"""Tests for the RAG engine's pure reranking logic (no ChromaDB needed)."""

from agent.rag import _keyword_boost


def test_keyword_boost_promotes_term_matching_chunk():
    """A chunk that literally contains more query terms should outrank a chunk
    with a marginally higher vector score but no term overlap."""
    chunks = [
        {"id": "a", "content": "Our refund policy and pricing details", "score": 0.50},
        {"id": "b", "content": "completely unrelated filler text", "score": 0.55},
    ]
    out = _keyword_boost("refund pricing policy", chunks)
    assert out[0]["id"] == "a"


def test_keyword_boost_is_noop_without_meaningful_terms():
    """Short/stopword-only queries shouldn't reorder anything."""
    chunks = [
        {"id": "a", "content": "x", "score": 0.6},
        {"id": "b", "content": "y", "score": 0.4},
    ]
    out = _keyword_boost("a an", chunks)
    assert [c["id"] for c in out] == ["a", "b"]


def test_keyword_boost_keeps_scores_in_range():
    """Boost must never push a score above 1.0."""
    chunks = [{"id": "a", "content": "alpha beta gamma", "score": 0.95}]
    out = _keyword_boost("alpha beta gamma", chunks)
    assert out[0]["score"] <= 1.0
