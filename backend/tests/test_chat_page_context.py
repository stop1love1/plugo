"""The page body a client pushes into the system prompt: one clamp, both transports.

`page_context` arrives straight off the wire, so two things have to hold whatever a client
sends: the body is bounded before it reaches the prompt, and a value of the wrong *type*
fails closed instead of raising mid-request.

The body travels under `pageText` — the key the widget fills
(`frontend/src/widget/index.ts`), the key `docs/api-reference.md` documents, and the only
one `ChatAgent._build_system_prompt` reads. The WebSocket path used to clamp `"text"`
instead: a key nothing writes and nothing reads, so it never truncated anything while
reading as though the page body were bounded.
"""

import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi import WebSocketDisconnect

from agent.core import ChatAgent
from repositories import create_repos
from routers.chat import MAX_PAGE_TEXT_CHARS, _clamp_page_context

# What the agent itself slices the body down to before fencing it into the prompt.
AGENT_PAGE_TEXT_CHARS = 1500


class _StubProvider:
    """LLM stub — no network, and no knowledge lookup to satisfy."""

    supports_tools = False

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.last_usage: dict | None = None

    async def chat(self, messages: list[dict], system_prompt: str = "", tools: list[dict] | None = None) -> dict:
        return {"content": "Sure thing.", "tool_calls": [], "usage": None}

    async def stream(
        self, messages: list[dict], system_prompt: str = "", tools: list[dict] | None = None
    ) -> AsyncIterator[str]:
        yield "Sure thing."


class _FakeWebSocket:
    """Feeds `_run_websocket_chat` a scripted frame sequence, then disconnects."""

    def __init__(self, frames: list[dict]) -> None:
        self.headers: dict[str, str] = {}
        self.sent: list[dict] = []
        self._frames = list(frames)

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)

    async def receive_json(self) -> dict:
        if not self._frames:
            raise WebSocketDisconnect(code=1000)
        return self._frames.pop(0)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        pass


# --- The shared clamp -----------------------------------------------------------------


def test_clamp_truncates_the_key_that_actually_carries_the_body() -> None:
    clamped = _clamp_page_context(
        {
            "url": "https://example.com/docs",
            "title": "Docs",
            "pageText": "x" * (MAX_PAGE_TEXT_CHARS * 3),
        }
    )

    assert clamped["pageText"] == "x" * MAX_PAGE_TEXT_CHARS
    # Everything else about the context survives.
    assert clamped["url"] == "https://example.com/docs"
    assert clamped["title"] == "Docs"


def test_clamp_copies_rather_than_mutating_the_caller() -> None:
    original = {"pageText": "x" * (MAX_PAGE_TEXT_CHARS + 1)}

    clamped = _clamp_page_context(original)

    assert len(clamped["pageText"]) == MAX_PAGE_TEXT_CHARS
    assert len(original["pageText"]) == MAX_PAGE_TEXT_CHARS + 1


def test_clamp_is_a_no_op_at_and_below_the_limit() -> None:
    at_limit = {"pageText": "x" * MAX_PAGE_TEXT_CHARS}
    assert _clamp_page_context(at_limit) is at_limit
    assert _clamp_page_context({"pageText": "short"}) == {"pageText": "short"}
    # `"text"` is not the key the prompt reads, so it is carried through untouched — the
    # old WS clamp bounded this and only this, which is why it never fired.
    passthrough = {"text": "y" * (MAX_PAGE_TEXT_CHARS * 2)}
    assert _clamp_page_context(passthrough) is passthrough


def test_clamp_drops_a_page_context_that_is_not_a_dict() -> None:
    for junk in ("a string", 42, ["a", "list"], None):
        assert _clamp_page_context(junk) is None


# --- The WebSocket turn loop applies it -----------------------------------------------


@pytest.mark.asyncio
async def test_websocket_bounds_the_page_body_on_every_turn(test_site: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    """Both WS entry points into `_handle_message` clamp: the first frame and the loop.

    The first-message path exists so a chat frame sent before any `init` is still handled;
    it has always mirrored the loop's message-size guard, and it has to mirror this one too
    or it is simply the unbounded way in.
    """
    monkeypatch.setattr("agent.core.get_llm_provider", lambda *a, **k: _StubProvider())
    # The session-end memory extraction is real; keep it off the network.
    monkeypatch.setattr("routers.chat.get_llm_provider", lambda *a, **k: _StubProvider())

    received: list[dict | None] = []

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
        received.append(page_context)
        return "system prompt", [], True

    monkeypatch.setattr(ChatAgent, "_build_system_prompt", _fake_build_system_prompt)

    from routers.chat import _background_tasks, _run_websocket_chat

    baseline = set(_background_tasks)
    oversized = {"url": "https://example.com/docs", "pageText": "x" * (MAX_PAGE_TEXT_CHARS * 3)}
    websocket = _FakeWebSocket(frames=[{"message": "second", "pageContext": dict(oversized)}])
    ws_repos = await create_repos()
    await _run_websocket_chat(
        websocket,
        ws_repos,
        {**test_site, "is_approved": True},
        test_site["token"],
        first_data={"message": "first", "pageContext": dict(oversized)},
    )
    # The session-end extraction is fired-and-forgotten; don't leave it on a closing loop.
    pending = [task for task in _background_tasks if task not in baseline]
    if pending:
        _, still_running = await asyncio.wait(pending, timeout=10.0)
        assert not still_running, f"background tasks still running: {still_running}"

    assert len(received) == 2, "both the first frame and the loop frame must reach the agent"
    for page_context in received:
        assert page_context["pageText"] == "x" * MAX_PAGE_TEXT_CHARS
        assert page_context["url"] == "https://example.com/docs"


# --- The agent's own read of the body -------------------------------------------------


@pytest.mark.asyncio
async def test_build_system_prompt_survives_a_non_string_page_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """A client can send anything under `pageText`; slicing a non-string raises TypeError.

    The clamp guards with `isinstance` and so passes a bad value straight through — the
    read site is where it has to fail closed, because that slice sits outside any `try`
    and would abort the visitor's turn.
    """
    monkeypatch.setattr("agent.core.get_llm_provider", lambda *a, **k: _StubProvider())
    monkeypatch.setattr("agent.core.embed_cache.get", lambda query: [0.1, 0.2, 0.3])

    async def _no_chunks(site_id: str, query_embedding: list[float], top_k: int = 10, **kwargs: object) -> list[dict]:
        return []

    monkeypatch.setattr("agent.core.rag_engine.search", _no_chunks)

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://example.com")

    for bad_body in (12345, ["a", "list"], {"nested": "object"}, None, True):
        prompt, _tools, _has_knowledge = await agent._build_system_prompt(
            "what is on this page?",
            page_context={"url": "https://example.com/docs", "pageText": bad_body},
        )
        # The turn survives, and the rest of the context still reaches the prompt.
        assert "https://example.com/docs" in prompt
        assert "- Page content:\n" in prompt, "the bad body drops out, the section stays"


@pytest.mark.asyncio
async def test_build_system_prompt_still_truncates_a_long_string_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard must not cost the agent its own bound on an ordinary string body."""
    monkeypatch.setattr("agent.core.get_llm_provider", lambda *a, **k: _StubProvider())
    monkeypatch.setattr("agent.core.embed_cache.get", lambda query: [0.1, 0.2, 0.3])

    async def _no_chunks(site_id: str, query_embedding: list[float], top_k: int = 10, **kwargs: object) -> list[dict]:
        return []

    monkeypatch.setattr("agent.core.rag_engine.search", _no_chunks)

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://example.com")

    prompt, _tools, _has_knowledge = await agent._build_system_prompt(
        "what is on this page?",
        page_context={"url": "https://example.com/docs", "pageText": "z" * (AGENT_PAGE_TEXT_CHARS * 2)},
    )

    assert "z" * AGENT_PAGE_TEXT_CHARS in prompt
    assert "z" * (AGENT_PAGE_TEXT_CHARS + 1) not in prompt
