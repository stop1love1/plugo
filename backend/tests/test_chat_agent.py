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


class FakeRepos:
    def __init__(self, chunks):
        self.knowledge = FakeKnowledgeRepo(chunks)
        self.tools = self

    async def list_enabled_by_site(self, site_id):
        return []


@pytest.mark.asyncio
async def test_get_response_returns_fallback_without_knowledge(monkeypatch):
    """Agent should refuse to guess when no knowledge chunks match."""

    monkeypatch.setattr("agent.core.get_llm_provider", lambda *args, **kwargs: FailingProvider())
    monkeypatch.setattr("agent.core.embed_cache.get", lambda query: [0.1, 0.2, 0.3])

    async def fake_search(site_id, query_embedding, top_k=10):
        return []

    monkeypatch.setattr("agent.core.rag_engine.search", fake_search)

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn")

    response = await agent.get_response("Edusoft cung cấp giải pháp gì?")

    assert "Knowledge hiện tại của website" in response
    assert "không thể trả lời chính xác" in response


@pytest.mark.asyncio
async def test_get_response_ignores_stale_vector_chunks_missing_from_db(monkeypatch):
    """Agent should ignore stale vector hits that no longer exist in Knowledge DB."""

    monkeypatch.setattr("agent.core.get_llm_provider", lambda *args, **kwargs: FailingProvider())
    monkeypatch.setattr("agent.core.embed_cache.get", lambda query: [0.1, 0.2, 0.3])

    async def fake_search(site_id, query_embedding, top_k=10):
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

    assert "Knowledge hiện tại của website" in response
    assert "không thể trả lời chính xác" in response


@pytest.mark.asyncio
async def test_stream_response_returns_fallback_without_knowledge(monkeypatch):
    """Streaming should also stop hallucinations when no chunks are found."""

    monkeypatch.setattr("agent.core.get_llm_provider", lambda *args, **kwargs: FailingProvider())
    monkeypatch.setattr("agent.core.embed_cache.get", lambda query: [0.1, 0.2, 0.3])

    async def fake_search(site_id, query_embedding, top_k=10):
        return []

    monkeypatch.setattr("agent.core.rag_engine.search", fake_search)

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn")

    parts = []
    async for token in agent.stream_response("Edusoft cung cấp giải pháp gì?"):
        parts.append(token)

    response = "".join(parts)
    assert "Knowledge hiện tại của website" in response
    assert "không thể trả lời chính xác" in response


def test_detects_vietnamese_without_diacritics():
    """Fallback language detection should still recognize common Vietnamese without accents."""

    agent = ChatAgent(site_id="site-1", site_name="Demo Site", site_url="https://edusoft.vn")

    assert agent._is_likely_vietnamese("Edusoft cung cap giai phap gi?")
