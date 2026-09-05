"""Both chat transports must persist the agent's per-turn tool invocations.

`ChatAgent` accumulates executed tool calls on `last_tool_calls` (the same
pattern as `last_citations`); the WebSocket and SSE transports are responsible
for writing that onto the stored assistant message, which is the only place
`GET /api/analytics/tool-usage` can read it from. These tests drive each
transport's message-handling code directly — no live socket, no network — and
assert against what actually landed in the database.
"""

import json
from collections.abc import AsyncIterator

import pytest

from repositories import Repositories
from tests.conftest import _FakeWebSocket

TOOL_NAME = "lookup_order"


class _ToolCallingProvider:
    """LLM stub: requests one tool call on its first chat, then answers."""

    supports_tools = True

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.last_usage: dict = {"input_tokens": 10, "output_tokens": 5}
        self.chat_calls = 0

    async def chat(self, messages: list[dict], system_prompt: str, tools: list[dict] | None = None) -> dict:
        self.chat_calls += 1
        if self.chat_calls == 1:
            return {
                "content": "",
                "tool_calls": [{"id": "call-1", "name": TOOL_NAME, "arguments": {"order_id": "123"}}],
                "usage": self.last_usage,
            }
        return {"content": "Done.", "tool_calls": [], "usage": self.last_usage}

    async def stream(
        self, messages: list[dict], system_prompt: str, tools: list[dict] | None = None
    ) -> AsyncIterator[str]:
        for tok in ("Your", " order", " shipped."):
            yield tok


@pytest.fixture(autouse=True)
def _patch_agent_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate from real LLM/embedding/RAG/HTTP, and make every tool call succeed."""
    monkeypatch.setattr("agent.core.get_llm_provider", lambda *a, **k: _ToolCallingProvider())
    monkeypatch.setattr("agent.core.embed_cache.get", lambda q: [0.1, 0.2, 0.3])

    async def _no_chunks(site_id: str, query_embedding: list[float], top_k: int = 10, **kwargs: object) -> list[dict]:
        return []

    monkeypatch.setattr("agent.core.rag_engine.search", _no_chunks)

    async def _fake_execute_tool(tool_meta: dict, arguments: dict, timeout: float = 30.0) -> dict:
        return {"status_code": 200, "data": {"status": "shipped"}, "success": True}

    monkeypatch.setattr("agent.core.tool_executor.execute_tool", _fake_execute_tool)


async def _seed_tool(db_repos: Repositories, site_id: str) -> None:
    await db_repos.tools.create(
        {
            "site_id": site_id,
            "name": TOOL_NAME,
            "description": "Look up an order",
            "method": "GET",
            "url": "https://api.example.com/orders",
            "params_schema": {"order_id": {"type": "string", "description": "Order ID", "required": True}},
        }
    )


@pytest.mark.asyncio
async def test_websocket_persists_tool_calls_on_assistant_message(db_repos: Repositories, test_site: dict) -> None:
    from agent.core import ChatAgent
    from routers.chat import _handle_message

    await _seed_tool(db_repos, test_site["id"])
    session = await db_repos.chat_sessions.create({"site_id": test_site["id"]})

    agent = ChatAgent(
        site_id=test_site["id"],
        site_name=test_site["name"],
        site_url=test_site["url"],
        llm_provider="claude",
        llm_model=test_site["llm_model"],
    )
    messages: list[dict] = []

    await _handle_message(
        _FakeWebSocket(frames=[]),
        agent,
        db_repos,
        session["id"],
        messages,
        "where is order 123?",
        None,
    )

    stored = await db_repos.chat_sessions.get_by_id(session["id"])
    assistant = stored["messages"][-1]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"] == [{"name": TOOL_NAME, "success": True}]


@pytest.mark.asyncio
async def test_sse_persists_tool_calls_on_assistant_message(db_repos: Repositories, test_site: dict) -> None:
    """Drives `_chat_stream_core`'s generator directly — see test_chat_sse.py for why."""
    from starlette.requests import Request as StarletteRequest

    from routers.chat import invalidate_site_cache
    from routers.chat_sse import ChatSSERequest, _chat_stream_core
    from utils.rate_limit import acquire_sse_slot

    await db_repos.sites.update(test_site["id"], {"is_approved": True})
    invalidate_site_cache()
    await _seed_tool(db_repos, test_site["id"])

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [],
        "path": f"/api/chat/{test_site['token']}/stream",
        "query_string": b"",
    }

    async def _receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    assert await acquire_sse_slot(test_site["token"]) is True

    response = await _chat_stream_core(
        test_site["token"],
        ChatSSERequest(message="where is order 123?"),
        StarletteRequest(scope, _receive),
        db_repos,
    )

    events = [event async for event in response.body_iterator]
    done_events = [e for e in events if e.get("event") == "done"]
    assert done_events, f"no done event in: {events}"
    session_id = json.loads(done_events[-1]["data"])["session_id"]

    stored = await db_repos.chat_sessions.get_by_id(session_id)
    assistant = stored["messages"][-1]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"] == [{"name": TOOL_NAME, "success": True}]


@pytest.mark.asyncio
async def test_turn_without_tool_calls_persists_no_tool_key(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A turn where no tool ran must not add a `tool_calls` key at all — that absence
    is exactly what legacy sessions look like to the analytics reader."""
    from agent.core import ChatAgent
    from routers.chat import _handle_message

    class _NoToolProvider(_ToolCallingProvider):
        async def chat(self, messages: list[dict], system_prompt: str, tools: list[dict] | None = None) -> dict:
            return {"content": "Hi!", "tool_calls": [], "usage": self.last_usage}

    monkeypatch.setattr("agent.core.get_llm_provider", lambda *a, **k: _NoToolProvider())

    await _seed_tool(db_repos, test_site["id"])
    session = await db_repos.chat_sessions.create({"site_id": test_site["id"]})

    agent = ChatAgent(
        site_id=test_site["id"],
        site_name=test_site["name"],
        site_url=test_site["url"],
        llm_provider="claude",
        llm_model=test_site["llm_model"],
    )

    await _handle_message(_FakeWebSocket(frames=[]), agent, db_repos, session["id"], [], "hello there", None)

    stored = await db_repos.chat_sessions.get_by_id(session["id"])
    assistant = stored["messages"][-1]
    assert assistant["role"] == "assistant"
    assert "tool_calls" not in assistant
