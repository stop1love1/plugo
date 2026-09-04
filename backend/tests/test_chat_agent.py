"""Tests for chat agent fallback behavior."""

import os
import sys
from collections.abc import AsyncIterator

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.core import ChatAgent


class FailingProvider:
    async def chat(self, *args, **kwargs):
        raise AssertionError("LLM chat should not run without knowledge matches")

    async def stream(self, *args, **kwargs):
        raise AssertionError("LLM stream should not run without knowledge matches")
        yield ""


class FakeKnowledgeRepo:
    def __init__(self, chunks):
        self._chunks = chunks

    async def get_many(self, chunk_ids):
        return self._chunks


class FakeToolsRepo:
    def __init__(self, tools):
        self._tools = tools

    async def list_enabled_by_site(self, site_id):
        return self._tools


class FakeRepos:
    def __init__(self, chunks, tools=None):
        self.knowledge = FakeKnowledgeRepo(chunks)
        self.tools = FakeToolsRepo(tools or [])


class FakeToolProvider:
    """Stand-in provider that supports tool calling but never actually calls a tool.

    Used to prove the tool-calling path (provider.chat / provider.stream) is reached
    instead of the no-knowledge fallback returning early.
    """

    supports_tools = True

    def __init__(self):
        self.last_usage = None
        self._reply = "Sure, let me look into that for you."

    async def chat(self, *args, **kwargs):
        return {"content": self._reply, "tool_calls": [], "usage": None}

    async def stream(self, *args, **kwargs):
        for token in self._reply:
            yield token


class ToolCallingProvider:
    """Stand-in provider that scripts one tool call per chat round, then answers.

    ``tool_names[i]`` is the tool requested on the (i+1)-th ``chat`` call; once the
    script runs out the provider replies with no tool calls, ending the agent's loop.
    Used to exercise the agent's tool-execution loop end to end.
    """

    supports_tools = True

    def __init__(self, *tool_names: str) -> None:
        self.last_usage: dict | None = None
        self.chat_calls = 0
        self._tool_names: tuple[str, ...] = tool_names or ("lookup_order",)
        self._reply = "Your order is on its way."

    async def chat(self, messages: list[dict], system_prompt: str, tools: list[dict] | None = None) -> dict:
        self.chat_calls += 1
        if self.chat_calls <= len(self._tool_names):
            name = self._tool_names[self.chat_calls - 1]
            return {
                "content": "",
                "tool_calls": [{"id": f"call-{self.chat_calls}", "name": name, "arguments": {"order_id": "123"}}],
                "usage": None,
            }
        return {"content": self._reply, "tool_calls": [], "usage": None}

    async def stream(
        self, messages: list[dict], system_prompt: str, tools: list[dict] | None = None
    ) -> AsyncIterator[str]:
        for token in self._reply:
            yield token


ENABLED_TOOL = {
    "id": "tool-1",
    "name": "lookup_order",
    "description": "Look up an order by its ID",
    "method": "GET",
    "url": "https://api.example.com/orders/{order_id}",
    "params_schema": {"order_id": {"type": "string", "description": "Order ID", "required": True}},
    "auth_type": None,
    "auth_value": None,
    "headers": {},
}

SECOND_ENABLED_TOOL = {
    "id": "tool-2",
    "name": "cancel_order",
    "description": "Cancel an order by its ID",
    "method": "POST",
    "url": "https://api.example.com/orders/cancel",
    "params_schema": {"order_id": {"type": "string", "description": "Order ID", "required": True}},
    "auth_type": None,
    "auth_value": None,
    "headers": {},
}


@pytest.mark.asyncio
async def test_get_response_returns_fallback_without_knowledge(monkeypatch):
    """Agent should refuse to guess when no knowledge chunks match."""

    monkeypatch.setattr("agent.core.get_llm_provider", lambda *args, **kwargs: FailingProvider())
    monkeypatch.setattr("agent.core.embed_cache.get", lambda query: [0.1, 0.2, 0.3])

    async def fake_search(site_id, query_embedding, top_k=10, **kwargs):
        return []

    monkeypatch.setattr("agent.core.rag_engine.search", fake_search)

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn")

    response = await agent.get_response("Edusoft cung cấp giải pháp gì?")

    assert "chưa có thông tin" in response or "don't have information" in response


@pytest.mark.asyncio
async def test_get_response_ignores_stale_vector_chunks_missing_from_db(monkeypatch):
    """Agent should ignore stale vector hits that no longer exist in Knowledge DB."""

    monkeypatch.setattr("agent.core.get_llm_provider", lambda *args, **kwargs: FailingProvider())
    monkeypatch.setattr("agent.core.embed_cache.get", lambda query: [0.1, 0.2, 0.3])

    async def fake_search(site_id, query_embedding, top_k=10, **kwargs):
        return [
            {
                "id": "stale-chunk",
                "content": "Old stale content",
                "metadata": {"source_url": "https://stale.example.com", "title": "Stale"},
                "score": 0.95,
            }
        ]

    monkeypatch.setattr("agent.core.rag_engine.search", fake_search)

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn")
    repos = FakeRepos(chunks=[])

    response = await agent.get_response("Edusoft cung cấp giải pháp gì?", repos=repos)

    assert "chưa có thông tin" in response or "don't have information" in response


@pytest.mark.asyncio
async def test_stream_response_returns_fallback_without_knowledge(monkeypatch):
    """Streaming should also stop hallucinations when no chunks are found."""

    monkeypatch.setattr("agent.core.get_llm_provider", lambda *args, **kwargs: FailingProvider())
    monkeypatch.setattr("agent.core.embed_cache.get", lambda query: [0.1, 0.2, 0.3])

    async def fake_search(site_id, query_embedding, top_k=10, **kwargs):
        return []

    monkeypatch.setattr("agent.core.rag_engine.search", fake_search)

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn")

    parts = []
    async for token in agent.stream_response("Edusoft cung cấp giải pháp gì?"):
        parts.append(token)

    response = "".join(parts)
    assert "chưa có thông tin" in response or "don't have information" in response


@pytest.mark.asyncio
async def test_get_response_reaches_tool_path_without_knowledge_when_tools_available(monkeypatch):
    """Action Mode regression: a site with no knowledge match but a usable tool must
    reach the provider/tool-calling path instead of the canned no-knowledge fallback."""

    monkeypatch.setattr("agent.core.get_llm_provider", lambda *args, **kwargs: FakeToolProvider())
    monkeypatch.setattr("agent.core.embed_cache.get", lambda query: [0.1, 0.2, 0.3])

    async def fake_search(site_id, query_embedding, top_k=10, **kwargs):
        return []

    monkeypatch.setattr("agent.core.rag_engine.search", fake_search)

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn", llm_provider="claude")
    repos = FakeRepos(chunks=[], tools=[ENABLED_TOOL])

    response = await agent.get_response("Show me order #123", repos=repos)

    assert "chưa có thông tin" not in response
    assert "don't have information" not in response
    assert response == "Sure, let me look into that for you."


@pytest.mark.asyncio
async def test_get_response_still_falls_back_without_knowledge_and_without_tools(monkeypatch):
    """Preserved behaviour: with repos present but no enabled tools, the fallback still fires."""

    monkeypatch.setattr("agent.core.get_llm_provider", lambda *args, **kwargs: FailingProvider())
    monkeypatch.setattr("agent.core.embed_cache.get", lambda query: [0.1, 0.2, 0.3])

    async def fake_search(site_id, query_embedding, top_k=10, **kwargs):
        return []

    monkeypatch.setattr("agent.core.rag_engine.search", fake_search)

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn", llm_provider="claude")
    repos = FakeRepos(chunks=[], tools=[])

    response = await agent.get_response("Show me order #123", repos=repos)

    assert "chưa có thông tin" in response or "don't have information" in response


@pytest.mark.asyncio
async def test_stream_response_reaches_tool_path_without_knowledge_when_tools_available(monkeypatch):
    """Same regression as above, exercised through stream_response."""

    monkeypatch.setattr("agent.core.get_llm_provider", lambda *args, **kwargs: FakeToolProvider())
    monkeypatch.setattr("agent.core.embed_cache.get", lambda query: [0.1, 0.2, 0.3])

    async def fake_search(site_id, query_embedding, top_k=10, **kwargs):
        return []

    monkeypatch.setattr("agent.core.rag_engine.search", fake_search)

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn", llm_provider="claude")
    repos = FakeRepos(chunks=[], tools=[ENABLED_TOOL])

    parts = []
    async for token in agent.stream_response("Show me order #123", repos=repos):
        parts.append(token)

    response = "".join(parts)
    assert "chưa có thông tin" not in response
    assert "don't have information" not in response
    assert response == "Sure, let me look into that for you."


@pytest.mark.asyncio
async def test_stream_response_still_falls_back_without_knowledge_and_without_tools(monkeypatch):
    """Preserved behaviour: with repos present but no enabled tools, the fallback still fires."""

    monkeypatch.setattr("agent.core.get_llm_provider", lambda *args, **kwargs: FailingProvider())
    monkeypatch.setattr("agent.core.embed_cache.get", lambda query: [0.1, 0.2, 0.3])

    async def fake_search(site_id, query_embedding, top_k=10, **kwargs):
        return []

    monkeypatch.setattr("agent.core.rag_engine.search", fake_search)

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn", llm_provider="claude")
    repos = FakeRepos(chunks=[], tools=[])

    parts = []
    async for token in agent.stream_response("Show me order #123", repos=repos):
        parts.append(token)

    response = "".join(parts)
    assert "chưa có thông tin" in response or "don't have information" in response


def _patch_no_knowledge(monkeypatch: pytest.MonkeyPatch, provider: ToolCallingProvider) -> None:
    """Wire an agent up with a stub provider and an empty knowledge base."""
    monkeypatch.setattr("agent.core.get_llm_provider", lambda *args, **kwargs: provider)
    monkeypatch.setattr("agent.core.embed_cache.get", lambda query: [0.1, 0.2, 0.3])

    async def fake_search(site_id: str, query_embedding: list[float], top_k: int = 10, **kwargs: object) -> list[dict]:
        return []

    monkeypatch.setattr("agent.core.rag_engine.search", fake_search)


def _patch_execute_tool(monkeypatch: pytest.MonkeyPatch, result: dict) -> list[tuple[str, dict]]:
    """Replace the real HTTP tool executor; returns a log of (url, arguments)."""
    seen: list[tuple[str, dict]] = []

    async def fake_execute_tool(tool_meta: dict, arguments: dict, timeout: float = 30.0) -> dict:
        seen.append((tool_meta["url"], arguments))
        return result

    monkeypatch.setattr("agent.core.tool_executor.execute_tool", fake_execute_tool)
    return seen


@pytest.mark.asyncio
async def test_get_response_records_successful_tool_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tool that ran successfully is recorded on the agent's per-turn accumulator."""

    _patch_no_knowledge(monkeypatch, ToolCallingProvider())
    seen = _patch_execute_tool(monkeypatch, {"status_code": 200, "data": {"ok": True}, "success": True})

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn", llm_provider="claude")
    repos = FakeRepos(chunks=[], tools=[ENABLED_TOOL])

    await agent.get_response("Show me order #123", repos=repos)

    assert len(seen) == 1
    assert agent.last_tool_calls == [{"name": "lookup_order", "success": True}]


@pytest.mark.asyncio
async def test_get_response_records_failed_tool_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tool whose execution failed is recorded with success=False."""

    _patch_no_knowledge(monkeypatch, ToolCallingProvider())
    _patch_execute_tool(monkeypatch, {"error": "Request timed out", "success": False})

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn", llm_provider="claude")
    repos = FakeRepos(chunks=[], tools=[ENABLED_TOOL])

    await agent.get_response("Show me order #123", repos=repos)

    assert agent.last_tool_calls == [{"name": "lookup_order", "success": False}]


@pytest.mark.asyncio
async def test_stream_response_records_tool_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """The streaming path records tool invocations too."""

    _patch_no_knowledge(monkeypatch, ToolCallingProvider())
    _patch_execute_tool(monkeypatch, {"status_code": 200, "data": {}, "success": True})

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn", llm_provider="claude")
    repos = FakeRepos(chunks=[], tools=[ENABLED_TOOL])

    async for _token in agent.stream_response("Show me order #123", repos=repos):
        pass

    assert agent.last_tool_calls == [{"name": "lookup_order", "success": True}]


@pytest.mark.asyncio
async def test_hallucinated_tool_name_is_not_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tool name with no matching _meta never ran, so it must not be counted."""

    _patch_no_knowledge(monkeypatch, ToolCallingProvider("teleport_customer"))

    async def never_called(tool_meta: dict, arguments: dict, timeout: float = 30.0) -> dict:
        raise AssertionError("execute_tool must not run for an unknown tool")

    monkeypatch.setattr("agent.core.tool_executor.execute_tool", never_called)

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn", llm_provider="claude")
    repos = FakeRepos(chunks=[], tools=[ENABLED_TOOL])

    await agent.get_response("Show me order #123", repos=repos)

    assert agent.last_tool_calls == []


@pytest.mark.asyncio
async def test_tool_calls_reset_between_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each turn reports only its own tool calls — like last_citations."""

    provider = ToolCallingProvider()
    _patch_no_knowledge(monkeypatch, provider)
    _patch_execute_tool(monkeypatch, {"status_code": 200, "data": {}, "success": True})

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn", llm_provider="claude")
    repos = FakeRepos(chunks=[], tools=[ENABLED_TOOL])

    await agent.get_response("Show me order #123", repos=repos)
    assert len(agent.last_tool_calls) == 1

    # Second turn: the provider has moved past its scripted tool call, so no tool runs.
    await agent.get_response("Thanks, anything else?", repos=repos)
    assert agent.last_tool_calls == []


@pytest.mark.asyncio
async def test_tool_calls_accumulate_across_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tool loop can run several rounds in one turn — every executed call is
    appended, in call order, each with its own outcome."""

    _patch_no_knowledge(monkeypatch, ToolCallingProvider("lookup_order", "cancel_order"))

    async def fake_execute_tool(tool_meta: dict, arguments: dict, timeout: float = 30.0) -> dict:
        # Distinct outcomes per tool, so a shared/last-write-wins bug can't pass.
        if tool_meta["url"] == SECOND_ENABLED_TOOL["url"]:
            return {"error": "Request timed out", "success": False}
        return {"status_code": 200, "data": {}, "success": True}

    monkeypatch.setattr("agent.core.tool_executor.execute_tool", fake_execute_tool)

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn", llm_provider="claude")
    repos = FakeRepos(chunks=[], tools=[ENABLED_TOOL, SECOND_ENABLED_TOOL])

    # Exercised through stream_response — the path both shipping transports use.
    async for _token in agent.stream_response("Show me order #123", repos=repos):
        pass

    assert agent.last_tool_calls == [
        {"name": "lookup_order", "success": True},
        {"name": "cancel_order", "success": False},
    ]


def test_detects_vietnamese_without_diacritics():
    """Fallback language detection should still recognize common Vietnamese without accents."""

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn")

    assert agent._is_likely_vietnamese("Edusoft cung cap giai phap gi?")


@pytest.mark.parametrize(
    "text, expected",
    [
        # Vietnamese with diacritics.
        ("Bạn có thể cho tôi biết giải pháp không?", True),
        # Vietnamese typed without diacritics, caught by the existing word markers.
        ("cung cap giai phap gi", True),
        # Plain English.
        ("What time do you open tomorrow?", False),
        # Japanese — a non-ASCII language that must NOT get the Vietnamese fallback.
        ("こんにちは、営業時間を教えてください", False),
        # Korean.
        ("안녕하세요, 영업시간이 어떻게 되나요?", False),
        # Chinese.
        ("你好, 请问营业时间是几点?", False),
        # Accented French — uses the shared Latin diacritics (à, é, è, ê, â, î) that
        # this detector must not treat as Vietnamese-exclusive.
        ("Où est le café ? C'est très intéressant et généreux.", False),
    ],
)
def test_is_likely_vietnamese_language_table(text: str, expected: bool) -> None:
    """`_is_likely_vietnamese` must key off Vietnamese's distinctive diacritics/words,
    not merely "contains a non-ASCII character" — otherwise every non-English,
    non-Vietnamese visitor (JA/KO/ZH/FR/...) wrongly gets the Vietnamese fallback."""

    assert ChatAgent._is_likely_vietnamese(text) is expected
