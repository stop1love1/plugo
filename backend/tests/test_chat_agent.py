"""Tests for chat agent fallback behavior."""

import os
import sys

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


def test_detects_vietnamese_without_diacritics():
    """Fallback language detection should still recognize common Vietnamese without accents."""

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn")

    assert agent._is_likely_vietnamese("Edusoft cung cap giai phap gi?")
