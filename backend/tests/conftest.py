"""Shared test fixtures for the Plugo backend."""

import asyncio
import contextlib
import os
import sys
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from fastapi import WebSocketDisconnect
from httpx import ASGITransport, AsyncClient
from starlette.datastructures import Address

# Add backend directory to path so imports work.
#
# Deliberately NOT normalized — do not "tidy" this to abspath()/resolve(). The
# literal `tests/..` prefix ends up on `config.__file__`, and `config.py`'s
# `_dotenv` block relies on it: `Path(...).parent.parent` walks `..` lexically,
# so the project-root `.env` is missed and a developer's real USERNAME/PASSWORD
# never reach `Settings`. Normalizing this line would silently start feeding
# untracked per-developer secrets into the suite. See the comment on `_dotenv` in
# `backend/config.py`, which explains the contract this line half-implements.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Override env before importing app
os.environ["DATABASE_PROVIDER"] = "sqlite"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test.db"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["CHROMA_PATH"] = "./data/test_chroma"
# Admin credentials: config.json ships with empty values and the backend refuses
# to start with empty or legacy-default ("pluginme") credentials. Patch the
# loaded settings with a dedicated test credential after import.
from config import settings as _settings

_settings.admin_username = "plugo"
_settings.admin_password = "test-admin-password"

# Ensure data dir exists
os.makedirs(os.path.join(os.path.dirname(__file__), "..", "data"), exist_ok=True)

_db_initialized = False


async def _ensure_db():
    global _db_initialized
    if not _db_initialized:
        # Import all models so Base.metadata knows about all tables
        import models  # noqa: F401
        from database import Base, engine

        # Drop and recreate all tables to ensure schema is up-to-date
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        _db_initialized = True


@pytest.fixture
def anyio_backend():
    return "asyncio"


# Both fixtures below deliberately import *unguarded*. They used to sit behind
# `contextlib.suppress(Exception)`, which made the failure they most need to
# survive — the imported name being renamed or moved — turn them into silent
# no-ops: cross-test contamination would return with the suite still green.
# Narrowing to `ImportError` would not have helped, since `from x import y` on a
# missing `y` raises exactly that. Let them raise instead: if either import ever
# breaks, every test errors at once and names the missing symbol, which is a far
# cheaper failure than the isolation quietly going away.


@pytest.fixture(autouse=True)
def _disable_rate_limiter():
    """slowapi's limiter state is process-global (app + limiter are module-cached),
    so per-window limits would otherwise leak across tests and make ordering matter.
    Disable it by default; tests that specifically exercise rate limiting flip it
    back on locally inside the test body."""
    from main import limiter

    limiter.enabled = False
    yield


@pytest.fixture(autouse=True)
def _reset_ws_ip_ceiling():
    """`utils.rate_limit`'s WebSocket per-address ceiling is process-global too,
    and it has no `enabled` switch — it is a hand-rolled window, not slowapi. Every
    fake socket that doesn't name an address presents the same `127.0.0.1`
    fallback, so one transport test's messages would otherwise count against a
    later one's. Rebuild it with the configured limits before each test; the
    ceiling's own tests shrink it inside their bodies, and this puts it back."""
    from utils.rate_limit import _reset_ws_ip_ceiling_for_tests

    _reset_ws_ip_ceiling_for_tests()
    yield


@pytest.fixture
async def client():
    """Create an async test client for the FastAPI app."""
    await _ensure_db()
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_repos():
    """Get repository instances for direct DB manipulation in tests."""
    await _ensure_db()
    from repositories import create_repos

    return await create_repos()


@pytest.fixture
async def auth_headers():
    """Return Authorization headers with a valid JWT token."""
    from auth import create_access_token

    token = create_access_token(subject="plugo", role="admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def test_site(db_repos, auth_headers):
    """Create a test site and return its data."""
    site = await db_repos.sites.create(
        {
            "name": "Test Site",
            "url": "https://example.com",
            "llm_provider": "claude",
            "llm_model": "claude-sonnet-4-20250514",
            "primary_color": "#6366f1",
            "greeting": "Hello!",
            "allowed_domains": "",
        }
    )
    yield site
    # Cleanup
    with contextlib.suppress(Exception):
        await db_repos.sites.delete(site["id"])


# --- Draining `_fire_and_forget` background tasks (shared by the transport tests) -------
#
# `routers.chat._background_tasks` is a module global whose entries are only discarded by
# a done callback, so a task another test left behind on a now-closed loop would never
# clear. Snapshotting a baseline before dispatch and draining only what's new afterwards
# keeps that foreign state out of the picture. A task of ours that genuinely overruns the
# deadline is a failure, not something to proceed past silently.


def _background_task_baseline() -> set[asyncio.Task]:
    """Snapshot `routers.chat._background_tasks` so a drain can ignore foreign tasks."""
    from routers.chat import _background_tasks

    return set(_background_tasks)


async def _drain_background_tasks(baseline: set[asyncio.Task], timeout: float = 10.0) -> None:
    """Await the `_fire_and_forget` tasks started since `baseline`."""
    from routers.chat import _background_tasks

    pending = [task for task in _background_tasks if task not in baseline]
    if not pending:
        return
    _, still_running = await asyncio.wait(pending, timeout=timeout)
    if still_running:
        raise AssertionError(f"background tasks still running after {timeout}s: {still_running}")


# --- LLM provider / WebSocket test doubles shared by the transport tests ----------------


class _StubProvider:
    """LLM stub for the chat agent, the summarizer, and the memory extractor.

    `chat_content` is what `.chat()` answers with — parameterised because
    `test_conversation_trim.py` drives the real summarizer through this stub and asserts on
    the text it returns, while the other callers only need it to stay off the network.
    """

    supports_tools = False

    def __init__(self, *args: object, chat_content: str = "Sure thing.", **kwargs: object) -> None:
        self.last_usage: dict | None = None
        self._chat_content = chat_content

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> dict:
        return {"content": self._chat_content, "tool_calls": [], "usage": None}

    async def stream(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        yield "Sure thing."


def _patch_stub_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the turn loop off the network: stub provider, no retrieval.

    Lives here beside `_StubProvider`, which is what it patches in — every WS transport
    test that drives a real turn loop needs exactly this pair, and it was copied
    verbatim into each of them before.
    """
    from agent.core import ChatAgent

    monkeypatch.setattr("agent.core.get_llm_provider", lambda *a, **k: _StubProvider())

    async def _fake_build_system_prompt(
        self: ChatAgent,
        query: str,
        page_context: dict | None = None,
        repos: object = None,
        visitor_id: str | None = None,
        conversation_summary: str | None = None,
    ) -> tuple[str, list[dict], bool]:
        self.last_citations = []
        self.last_tool_calls = []
        return "system prompt", [], True

    monkeypatch.setattr(ChatAgent, "_build_system_prompt", _fake_build_system_prompt)


class _FakeWebSocket:
    """Feeds `_run_websocket_chat` (or `_handle_message` directly) a scripted frame
    sequence, then disconnects.

    `on_receive` runs before each frame is served (including the eventual disconnect) —
    tests use it to drain background tasks deterministically between turns, without
    depending on a real event-loop yield to interleave them.

    `client_host` fills the peer address the WS per-address ceiling reads via
    `utils.rate_limit.ws_client_ip`; it is the only way to drive that ceiling from
    more than one source in-process, mirroring the `client=` argument
    `test_rate_limit_public.py` hands `ASGITransport`. Left unset, `client` is None
    and `ws_client_ip` maps it to `127.0.0.1`, exactly as slowapi's
    `get_remote_address` does for a scope without a client.
    """

    def __init__(
        self,
        frames: list[dict],
        on_receive: Callable[[], Awaitable[None]] | None = None,
        client_host: str | None = None,
    ) -> None:
        self.headers: dict[str, str] = {}
        self.client: Address | None = Address(client_host, 12345) if client_host else None
        self.sent: list[dict] = []
        self.closed: list[tuple[int, str]] = []
        self._frames = list(frames)
        self._on_receive = on_receive

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)

    async def receive_json(self) -> dict:
        if self._on_receive is not None:
            await self._on_receive()
        if not self._frames:
            raise WebSocketDisconnect(code=1000)
        return self._frames.pop(0)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed.append((code, reason))
