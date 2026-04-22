"""Tests for the SSE /api/chat/{site_token}/stream endpoint.

Covers the happy-path stream (tokens + citations + done), per-site origin
enforcement (C-4 isolation), token-usage persistence after a completed
stream, invalid/unapproved sites (404/403), and the per-token concurrency
cap (429). The LLM, embedding cache, and RAG search are all mocked so no
network call ever fires.
"""

import uuid

import pytest

# Distinct from other files' chunk ids — tests share a single sqlite DB
# and the PRIMARY KEY collides if two files seed the same id.
_REF_CHUNK_ID = f"chunk-{uuid.uuid4().hex[:8]}-sse"


class _FakeChatProvider:
    """Streaming LLM stub — emits a handful of tokens without touching the network."""

    def __init__(self, *args, **kwargs):
        self.last_usage = {"input_tokens": 10, "output_tokens": 5}

    async def chat(self, messages, system_prompt, tools=None):
        return {"content": "stub", "tool_calls": [], "usage": self.last_usage}

    async def stream(self, messages, system_prompt, tools=None):
        for tok in ("Hello", " ", "world"):
            yield tok


async def _fake_search(site_id, query_embedding, top_k=10):
    """Return one chunk so the agent doesn't bail on 'no knowledge'."""
    return [
        {
            "id": _REF_CHUNK_ID,
            "content": "Example knowledge content.",
            "metadata": {"source_url": "https://example.com/docs", "title": "Docs"},
            "score": 0.82,
        }
    ]


@pytest.fixture(autouse=True)
def _patch_llm_and_rag(monkeypatch):
    """Isolate the SSE tests from real LLM/embedding/RAG dependencies."""
    monkeypatch.setattr("agent.core.get_llm_provider", lambda *a, **k: _FakeChatProvider())
    monkeypatch.setattr("agent.core.embed_cache.get", lambda q: [0.1, 0.2, 0.3])
    monkeypatch.setattr("agent.core.rag_engine.search", _fake_search)


async def _approve_site(db_repos, site_id: str) -> None:
    await db_repos.sites.update(site_id, {"is_approved": True})


async def _seed_ref_chunk(db_repos, site_id: str, chunk_id: str = _REF_CHUNK_ID) -> None:
    """Persist the chunk the fake search returns so citation resolution succeeds."""
    existing = await db_repos.knowledge.get_by_id(chunk_id)
    if existing:
        return
    await db_repos.knowledge.create({
        "id": chunk_id,
        "site_id": site_id,
        "source_url": "https://example.com/docs",
        "source_type": "crawl",
        "title": "Docs",
        "content": "Example knowledge content.",
        "chunk_index": 0,
        "content_hash": f"h-{chunk_id[:8]}",
    })


@pytest.mark.asyncio
async def test_sse_stream_emits_tokens_citations_done(client, db_repos, test_site):
    await _approve_site(db_repos, test_site["id"])
    await _seed_ref_chunk(db_repos, test_site["id"])
    token = test_site["token"]

    async with client.stream(
        "POST",
        f"/api/chat/{token}/stream",
        json={"message": "hi"},
    ) as resp:
        assert resp.status_code == 200
        # sse-starlette sets `text/event-stream` with an encoding hint.
        assert resp.headers["content-type"].startswith("text/event-stream")
        body_chunks = []
        async for chunk in resp.aiter_text():
            body_chunks.append(chunk)
            # Stop once we've seen the done event so the test doesn't hang on keep-alives.
            if "event: done" in "".join(body_chunks):
                break

    body = "".join(body_chunks)
    assert "event: token" in body
    # Citations event should be present since _fake_search returns a URL-bearing chunk.
    assert "event: citations" in body
    assert "event: done" in body


@pytest.mark.asyncio
async def test_sse_bad_site_token_returns_404(client):
    resp = await client.post(
        "/api/chat/bogus-token/stream",
        json={"message": "hi"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sse_not_approved_site_returns_403(client, test_site):
    # Fresh site from fixture has is_approved=False by default.
    resp = await client.post(
        f"/api/chat/{test_site['token']}/stream",
        json={"message": "hi"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sse_origin_required_when_domains_configured(client, db_repos, test_site):
    """If `allowed_domains` is set, requests without an Origin header must 403."""
    await _approve_site(db_repos, test_site["id"])
    await db_repos.sites.update(test_site["id"], {"allowed_domains": "example.com"})
    # Invalidate the site cache so the update is visible to the endpoint.
    from routers.chat import invalidate_site_cache
    invalidate_site_cache()

    resp = await client.post(
        f"/api/chat/{test_site['token']}/stream",
        json={"message": "hi"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sse_origin_mismatch_returns_403(client, db_repos, test_site):
    await _approve_site(db_repos, test_site["id"])
    await db_repos.sites.update(test_site["id"], {"allowed_domains": "example.com"})
    from routers.chat import invalidate_site_cache
    invalidate_site_cache()

    resp = await client.post(
        f"/api/chat/{test_site['token']}/stream",
        json={"message": "hi"},
        headers={"Origin": "https://evil.com"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sse_token_usage_persisted_via_core(db_repos, test_site, monkeypatch):
    """Exercise `_chat_stream_core` + the generator directly — no EventSourceResponse.

    sse-starlette's process-wide `AppStatus.should_exit_event` binds to the
    first event loop it sees. A second streaming request (from another test
    file) would trip on `bound to a different event loop`. Driving the inner
    generator ourselves avoids that while still proving the router path
    persists `tokens_input`/`tokens_output` after a completed stream.
    """
    from starlette.requests import Request as StarletteRequest

    from routers.chat_sse import ChatSSERequest, _chat_stream_core

    await _approve_site(db_repos, test_site["id"])
    # Seed a chunk whose id is stable across the module so citations resolve.
    await _seed_ref_chunk(db_repos, test_site["id"])

    # Minimal ASGI Request stub — the core function only reads `headers.get("origin")`.
    scope = {
        "type": "http",
        "method": "POST",
        "headers": [],
        "path": f"/api/chat/{test_site['token']}/stream",
        "query_string": b"",
    }

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = StarletteRequest(scope, _receive)

    # The core acquires an SSE slot on enter and releases on generator end —
    # mirror the endpoint's contract here.
    from utils.rate_limit import acquire_sse_slot
    assert await acquire_sse_slot(test_site["token"]) is True

    response = await _chat_stream_core(
        test_site["token"],
        ChatSSERequest(message="hello"),
        request,
        db_repos,
    )

    # `response` is an EventSourceResponse whose body iterator is our
    # generator. Drain it by iterating body_iterator directly.
    events: list[dict] = []
    async for event in response.body_iterator:
        events.append(event)

    # `done` event carries the session_id.
    done_events = [e for e in events if e.get("event") == "done"]
    assert done_events, f"no done event in: {events}"
    import json
    session_id = json.loads(done_events[-1]["data"])["session_id"]

    session = await db_repos.chat_sessions.get_by_id(session_id)
    assert session is not None
    assert session["tokens_input"] > 0
    assert session["tokens_output"] > 0


@pytest.mark.asyncio
async def test_sse_concurrency_guard_rejects_over_cap(client, db_repos, test_site):
    """With the concurrency guard capped at 2, the 3rd simultaneous stream must 429.

    We acquire two slots directly against the module-level guard (simulating
    two open streams), then fire a real HTTP request through the endpoint and
    assert it's rejected with 429 before any streaming starts. After releasing
    the held slots, a fresh request is accepted again.

    Doing it this way (direct acquire rather than holding two live streams)
    avoids the sse-starlette AppStatus event-loop entanglement that makes
    multi-stream tests flaky under httpx's ASGI transport, while still
    exercising the exact endpoint code path that performs the 429.
    """
    from utils import rate_limit as rl_mod

    # Cap the guard at 2 for this test; restore afterwards.
    original_guard = rl_mod._sse_guard
    rl_mod._reset_sse_guard_for_tests(max_per_token=2)

    try:
        await _approve_site(db_repos, test_site["id"])
        token = test_site["token"]

        # Simulate two already-open SSE streams on this token.
        assert await rl_mod.acquire_sse_slot(token) is True
        assert await rl_mod.acquire_sse_slot(token) is True
        assert rl_mod.sse_active_count(token) == 2

        # A third acquire would be rejected at the guard level.
        assert await rl_mod.acquire_sse_slot(token) is False

        # And the HTTP endpoint surfaces that as a 429, never reaching the
        # stream body (the site_token is valid and approved, so a 404/403
        # would indicate the guard didn't fire).
        resp = await client.post(
            f"/api/chat/{token}/stream",
            json={"message": "hi"},
        )
        assert resp.status_code == 429

        # Release one slot — a new request should now be accepted by the guard
        # (we don't actually run it through the endpoint because stream-body
        # exercising is covered by the other SSE test; here we're only proving
        # the cap is dynamic).
        await rl_mod.release_sse_slot(token)
        assert rl_mod.sse_active_count(token) == 1
        assert await rl_mod.acquire_sse_slot(token) is True
        assert rl_mod.sse_active_count(token) == 2

        # Clean up held slots so we don't leak into the next test.
        await rl_mod.release_sse_slot(token)
        await rl_mod.release_sse_slot(token)
        assert rl_mod.sse_active_count(token) == 0
    finally:
        rl_mod._sse_guard = original_guard


@pytest.mark.asyncio
async def test_site_token_key_isolates_tenants():
    """site_token_key returns `site:<token>` so tenants never share buckets.

    This is a unit-level assertion of the key_func contract — the integration
    behaviour (429 after N requests) is exercised by slowapi's own test suite.
    Duplicating it here in a full ASGI test proved flaky under httpx's async
    transport; the critical invariant is that two different site tokens
    produce different keys.
    """
    from unittest.mock import MagicMock

    from utils.rate_limit import site_token_key

    req_a = MagicMock()
    req_a.path_params = {"site_token": "token-a"}
    req_b = MagicMock()
    req_b.path_params = {"site_token": "token-b"}
    req_none = MagicMock()
    req_none.path_params = {}
    req_none.client = MagicMock(host="1.2.3.4")

    assert site_token_key(req_a) == "site:token-a"
    assert site_token_key(req_b) == "site:token-b"
    # Distinct buckets per token.
    assert site_token_key(req_a) != site_token_key(req_b)
    # No path param → degrade to IP.
    assert site_token_key(req_none) == "1.2.3.4"
