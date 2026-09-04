"""Tests for the SSE /api/chat/{site_token}/stream endpoint.

Covers the happy-path stream (tokens + citations + done), per-site origin
enforcement (C-4 isolation), token-usage persistence after a completed
stream, invalid/unapproved sites (404/403), and the per-token concurrency
cap (429). The LLM, embedding cache, and RAG search are all mocked so no
network call ever fires.

Also pins the parity SSE owes the WebSocket transport, since SSE is a documented
alternative and not a lesser one: the same message size limit, a bounded page body, the
stored conversation summary reaching the prompt, and background memory extraction and
summarization — the latter two on a cadence, since SSE has no session end to run them at,
and per-turn would bill the operator an LLM round trip for every visitor message.
"""

import asyncio
import json
import uuid

import pytest
from httpx import AsyncClient
from starlette.requests import Request as StarletteRequest

from agent.core import ChatAgent
from agent.memory import ConversationSummarizer
from repositories import Repositories
from routers.chat_sse import (
    MAX_MESSAGE_CHARS,
    MAX_PAGE_TEXT_CHARS,
    MEMORY_EXTRACT_EVERY_MESSAGES,
    ChatSSERequest,
)
from utils.rate_limit import acquire_sse_slot

# Distinct from other files' chunk ids — tests share a single sqlite DB
# and the PRIMARY KEY collides if two files seed the same id.
_REF_CHUNK_ID = f"chunk-{uuid.uuid4().hex[:8]}-sse"

_SUMMARY_TEXT = "The visitor asked about shipping and was told it takes three days."


class _FakeChatProvider:
    """Streaming LLM stub — emits a handful of tokens without touching the network."""

    def __init__(self, *args, **kwargs):
        self.last_usage = {"input_tokens": 10, "output_tokens": 5}

    async def chat(self, messages, system_prompt, tools=None):
        return {"content": "stub", "tool_calls": [], "usage": self.last_usage}

    async def stream(self, messages, system_prompt, tools=None):
        for tok in ("Hello", " ", "world"):
            yield tok


async def _fake_search(site_id, query_embedding, top_k=10, **kwargs):
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


def _asgi_request(site_token: str) -> StarletteRequest:
    """Minimal ASGI Request stub — the core function only reads `headers.get("origin")`."""
    scope = {
        "type": "http",
        "method": "POST",
        "headers": [],
        "path": f"/api/chat/{site_token}/stream",
        "query_string": b"",
    }

    async def _receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    return StarletteRequest(scope, _receive)


async def _run_core_stream(site_token: str, body: ChatSSERequest, repos: Repositories) -> list[dict]:
    """Drive `_chat_stream_core` and its generator directly; return the emitted events.

    sse-starlette's process-wide `AppStatus.should_exit_event` binds to the first event
    loop it sees, so a second streaming request (from another test file) would trip on
    `bound to a different event loop`. Driving the inner generator ourselves avoids that
    while still exercising the exact router path. The core acquires an SSE slot on entry
    and releases it when the generator ends — mirror the endpoint's contract here.
    """
    from routers.chat_sse import _chat_stream_core

    assert await acquire_sse_slot(site_token) is True
    response = await _chat_stream_core(site_token, body, _asgi_request(site_token), repos)
    return [event async for event in response.body_iterator]


def _record_agent_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Replace `_build_system_prompt` with a recorder of what each turn handed the agent."""
    calls: list[dict] = []

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
        calls.append(
            {
                "page_context": page_context,
                "conversation_summary": conversation_summary,
                "history": [dict(m) for m in self.messages],
            }
        )
        return "system prompt", [], True

    monkeypatch.setattr(ChatAgent, "_build_system_prompt", _fake_build_system_prompt)
    return calls


def _capture_background_helpers(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[dict]]:
    """Swap the two background helpers for recorders, leaving `_fire_and_forget` real.

    Dispatch is what's under test, so the tasks are still created and awaited — only the
    LLM-backed bodies are replaced.
    """
    calls: dict[str, list[dict]] = {"memories": [], "summarize": []}

    async def _fake_extract(visitor_id: str, site: dict, session_id: str, messages: list[dict]) -> None:
        calls["memories"].append({"visitor_id": visitor_id, "session_id": session_id, "messages": messages})

    async def _fake_summarize(
        session_id: str,
        site: dict,
        messages: list[dict],
        agent: ChatAgent | None = None,
        trim_boundary: dict | None = None,
    ) -> None:
        calls["summarize"].append(
            {
                "session_id": session_id,
                "messages": messages,
                "agent": agent,
                "trim_boundary": trim_boundary,
            }
        )

    monkeypatch.setattr("routers.chat_sse._extract_and_save_memories", _fake_extract)
    monkeypatch.setattr("routers.chat_sse._maybe_summarize", _fake_summarize)
    return calls


def _background_baseline() -> set[asyncio.Task]:
    """Snapshot `routers.chat._background_tasks` so a drain can ignore foreign tasks."""
    from routers.chat import _background_tasks

    return set(_background_tasks)


async def _drain_background(baseline: set[asyncio.Task], timeout: float = 10.0) -> None:
    """Await the `_fire_and_forget` tasks started since `baseline`.

    `_background_tasks` is a module global cleared only by a done callback, so a task
    another test left on a now-closed loop would never clear; waiting only on what this
    test started keeps that state out of the picture.
    """
    from routers.chat import _background_tasks

    pending = [task for task in _background_tasks if task not in baseline]
    if not pending:
        return
    _, still_running = await asyncio.wait(pending, timeout=timeout)
    if still_running:
        raise AssertionError(f"background tasks still running after {timeout}s: {still_running}")


def _stored_history(turns: int, unanswered_question: bool = False) -> list[dict]:
    """A persisted session's message list: alternating visitor/assistant turns.

    With `unanswered_question`, a trailing visitor message with no reply makes the count
    odd — what the WS path persists after a turn that streamed nothing (`routers/chat.py`
    appends the visitor's message unconditionally but saves only on non-empty output, so
    the *next* save writes the orphan too).
    """
    history: list[dict] = []
    for i in range(turns):
        history.append({"role": "user", "content": f"question {i}", "timestamp": "2026-01-01T00:00:00Z"})
        history.append({"role": "assistant", "content": f"answer {i}", "timestamp": "2026-01-01T00:00:01Z"})
    if unanswered_question:
        history.append({"role": "user", "content": "unanswered", "timestamp": "2026-01-01T00:00:02Z"})
    return history


async def _seed_session(db_repos: Repositories, site_id: str, turns: int, unanswered_question: bool = False) -> str:
    """Create a session for `site_id` carrying `turns` stored visitor/assistant turns."""
    session = await db_repos.chat_sessions.create({"site_id": site_id, "visitor_id": f"{site_id}:visitor-1"})
    history = _stored_history(turns, unanswered_question)
    if history:
        await db_repos.chat_sessions.update_messages(session["id"], history)
    return session["id"]


async def _seed_ref_chunk(db_repos, site_id: str, chunk_id: str = _REF_CHUNK_ID) -> None:
    """Persist the chunk the fake search returns so citation resolution succeeds."""
    existing = await db_repos.knowledge.get_by_id(chunk_id)
    if existing:
        return
    await db_repos.knowledge.create(
        {
            "id": chunk_id,
            "site_id": site_id,
            "source_url": "https://example.com/docs",
            "source_type": "crawl",
            "title": "Docs",
            "content": "Example knowledge content.",
            "chunk_index": 0,
            "content_hash": f"h-{chunk_id[:8]}",
        }
    )


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
async def test_sse_token_usage_persisted_via_core(db_repos, test_site):
    """Exercise `_chat_stream_core` + the generator directly — no EventSourceResponse.

    sse-starlette's process-wide `AppStatus.should_exit_event` binds to the
    first event loop it sees. A second streaming request (from another test
    file) would trip on `bound to a different event loop`. Driving the inner
    generator ourselves avoids that while still proving the router path
    persists `tokens_input`/`tokens_output` after a completed stream.
    """
    await _approve_site(db_repos, test_site["id"])
    # Seed a chunk whose id is stable across the module so citations resolve.
    await _seed_ref_chunk(db_repos, test_site["id"])

    events = await _run_core_stream(test_site["token"], ChatSSERequest(message="hello"), db_repos)

    # `done` event carries the session_id.
    done_events = [e for e in events if e.get("event") == "done"]
    assert done_events, f"no done event in: {events}"
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


# --- Parity with the WebSocket transport --------------------------------------------


@pytest.mark.asyncio
async def test_sse_oversized_message_rejected_and_nothing_persisted(
    client: AsyncClient, db_repos: Repositories, test_site: dict
) -> None:
    """A message past the WS ceiling must 422 before it can reach the LLM prompt.

    The rejection has to happen at validation, so the request must also leave no session
    behind — otherwise an attacker could still fill the sessions table one 422 at a time.
    """
    await _approve_site(db_repos, test_site["id"])

    resp = await client.post(
        f"/api/chat/{test_site['token']}/stream",
        json={"message": "x" * (MAX_MESSAGE_CHARS + 1)},
    )

    assert resp.status_code == 422
    assert await db_repos.chat_sessions.list_by_site(test_site["id"]) == []


@pytest.mark.asyncio
async def test_sse_message_at_limit_is_accepted(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The boundary itself is allowed — the limit must not be off by one."""
    await _approve_site(db_repos, test_site["id"])
    calls = _record_agent_calls(monkeypatch)

    events = await _run_core_stream(
        test_site["token"],
        ChatSSERequest(message="x" * MAX_MESSAGE_CHARS),
        db_repos,
    )

    assert [e for e in events if e.get("event") == "done"]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_sse_empty_message_returns_422(client: AsyncClient, db_repos: Repositories, test_site: dict) -> None:
    await _approve_site(db_repos, test_site["id"])

    resp = await client.post(f"/api/chat/{test_site['token']}/stream", json={"message": ""})

    assert resp.status_code == 422
    assert await db_repos.chat_sessions.list_by_site(test_site["id"]) == []


@pytest.mark.asyncio
async def test_sse_clamps_oversized_page_text(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`pageText` is the key that carries the page body, so that is the key we clamp.

    The widget fills it (`frontend/src/widget/index.ts`) and `_build_system_prompt` reads
    it; the WS path's `"text"` clamp matches neither and so never fires.
    """
    await _approve_site(db_repos, test_site["id"])
    calls = _record_agent_calls(monkeypatch)
    body = ChatSSERequest(
        message="hi",
        page_context={"url": "https://example.com/docs", "pageText": "x" * (MAX_PAGE_TEXT_CHARS * 3)},
    )

    await _run_core_stream(test_site["token"], body, db_repos)

    received = calls[0]["page_context"]
    assert received["pageText"] == "x" * MAX_PAGE_TEXT_CHARS
    # Everything else about the context survives the clamp.
    assert received["url"] == "https://example.com/docs"
    # And the clamp copies rather than mutating the caller's request model.
    assert len(body.page_context["pageText"]) == MAX_PAGE_TEXT_CHARS * 3


@pytest.mark.asyncio
async def test_sse_resumed_session_uses_stored_summary(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resumed SSE turn must send the stored summary *instead of* the history it covers.

    Sending both is what made summarization grow the prompt in the first place, so the
    replay is bounded by the summary row's `message_count_summarized` — which is why
    `restore_agent_history` takes the row and not just its text.
    """
    await _approve_site(db_repos, test_site["id"])
    session_id = await _seed_session(db_repos, test_site["id"], turns=12)  # 24 stored messages
    await db_repos.conversation_summaries.upsert_by_session(
        session_id,
        {
            "site_id": test_site["id"],
            "summary_text": _SUMMARY_TEXT,
            "message_count_summarized": 18,
            "total_message_count": 24,
        },
    )
    calls = _record_agent_calls(monkeypatch)

    await _run_core_stream(
        test_site["token"],
        ChatSSERequest(message="and now?", session_id=session_id),
        db_repos,
    )

    assert calls[0]["conversation_summary"] == _SUMMARY_TEXT
    # 24 stored - 18 summarized = the 6-message tail, plus this turn's question.
    history = calls[0]["history"]
    assert [m["content"] for m in history] == [
        "question 9",
        "answer 9",
        "question 10",
        "answer 10",
        "question 11",
        "answer 11",
        "and now?",
    ]


async def _run_turn_and_capture_background(
    db_repos: Repositories,
    test_site: dict,
    monkeypatch: pytest.MonkeyPatch,
    stored_turns: int,
    visitor_id: str | None = None,
    unanswered_question: bool = False,
) -> tuple[str, dict[str, list[dict]]]:
    """Run one SSE turn on a session already holding `stored_turns` turns.

    Returns the session id and what the two background helpers were handed, with the
    dispatched tasks already drained.
    """
    await _approve_site(db_repos, test_site["id"])
    session_id = await _seed_session(db_repos, test_site["id"], stored_turns, unanswered_question)
    _record_agent_calls(monkeypatch)
    calls = _capture_background_helpers(monkeypatch)
    baseline = _background_baseline()

    await _run_core_stream(
        test_site["token"],
        ChatSSERequest(message="next question", session_id=session_id, visitor_id=visitor_id),
        db_repos,
    )
    await _drain_background(baseline)
    return session_id, calls


@pytest.mark.asyncio
async def test_sse_extracts_memories_once_the_conversation_is_worth_it(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Visitor memory is a headline feature; SSE must feed it like a WS session does.

    The WS path extracts once, at session end, from a session holding at least 4 messages.
    SSE cannot know which turn is the last, so it extracts as soon as a conversation
    crosses that same floor — most widget conversations are short and would otherwise
    never reach a wider cadence at all.
    """
    session_id, calls = await _run_turn_and_capture_background(
        db_repos, test_site, monkeypatch, stored_turns=1, visitor_id="visitor-1"
    )

    assert len(calls["memories"]) == 1
    extraction = calls["memories"][0]
    assert extraction["session_id"] == session_id
    assert extraction["visitor_id"] == f"{test_site['id']}:visitor-1"
    # This turn's pair joins the two stored messages — the WS floor of 4.
    assert [m["content"] for m in extraction["messages"]] == [
        "question 0",
        "answer 0",
        "next question",
        "Hello world",
    ]
    # 4 messages is under the summarization threshold.
    assert calls["summarize"] == []


@pytest.mark.asyncio
async def test_sse_short_session_does_not_extract_memories(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Below the WS floor there is nothing worth an extraction call."""
    await _approve_site(db_repos, test_site["id"])
    _record_agent_calls(monkeypatch)
    calls = _capture_background_helpers(monkeypatch)
    baseline = _background_baseline()

    # A brand-new session ends this turn holding only the question and its answer.
    await _run_core_stream(test_site["token"], ChatSSERequest(message="hi"), db_repos)
    await _drain_background(baseline)

    assert calls["memories"] == []
    assert calls["summarize"] == []


@pytest.mark.asyncio
async def test_sse_does_not_extract_memories_on_every_turn(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Past the floor, extraction waits for the cadence.

    Extraction is a full LLM round trip billed to the site operator. Firing it on every
    turn would cost ~19 calls across a 20-turn conversation where the WS transport makes
    one — a 19x amplification for anyone who moves an embed from WS to SSE.
    """
    _, calls = await _run_turn_and_capture_background(db_repos, test_site, monkeypatch, stored_turns=2)

    # 4 stored + this turn's pair = 6: past the floor, short of the cadence.
    assert calls["memories"] == []
    assert calls["summarize"] == []


@pytest.mark.asyncio
async def test_sse_extracts_memories_again_on_the_cadence(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At the cadence it fires again, on the same beat as the summarizer."""
    session_id, calls = await _run_turn_and_capture_background(db_repos, test_site, monkeypatch, stored_turns=9)

    # 18 stored + this turn's pair = 20 = MEMORY_EXTRACT_EVERY_MESSAGES.
    assert len(calls["memories"]) == 1
    assert calls["memories"][0]["session_id"] == session_id
    assert len(calls["memories"][0]["messages"]) == MEMORY_EXTRACT_EVERY_MESSAGES
    # Extraction and summarization share the rhythm rather than running on two of them.
    assert len(calls["summarize"]) == 1


@pytest.mark.asyncio
async def test_sse_cadence_survives_an_odd_stored_message_count(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session whose stored count went odd must still hit the cadence.

    The WS path can persist an odd count (a turn that streamed nothing leaves the
    visitor's message to be saved alone), and the count stays odd for the rest of the
    session's life. A `stored % cadence == 0` test would then never fire again — not a
    skipped beat but a permanent one, silently ending memory extraction for that visitor.
    So the cadence asks whether this turn *crossed* a multiple, not whether it landed on
    one.
    """
    _, calls = await _run_turn_and_capture_background(
        db_repos, test_site, monkeypatch, stored_turns=9, unanswered_question=True
    )

    # 18 + the orphaned question = 19 stored, + this turn's pair = 21: past 20, never on it.
    assert len(calls["memories"]) == 1
    assert len(calls["memories"][0]["messages"]) == 21
    # Summarization deliberately keeps the WS turn loop's exact `% 20 == 0` test, so it
    # does not fire here — that parity is intentional and not this cadence's business.
    assert calls["summarize"] == []


@pytest.mark.asyncio
async def test_sse_summarizes_on_the_websocket_threshold(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every 20 stored messages, same as the WS turn loop.

    No `agent`/`trim_boundary` is passed: the SSE agent is discarded with the request, so
    staging a summary on it would trim history nothing reads again. SSE shrinks its prompt
    on the *next* request instead, where `restore_agent_history` bounds the replay by the
    stored row.
    """
    # 18 stored messages + this turn's pair = 20.
    session_id, calls = await _run_turn_and_capture_background(db_repos, test_site, monkeypatch, stored_turns=9)

    assert len(calls["summarize"]) == 1
    dispatch = calls["summarize"][0]
    assert dispatch["session_id"] == session_id
    assert len(dispatch["messages"]) == ConversationSummarizer.MESSAGE_THRESHOLD
    assert dispatch["agent"] is None
    assert dispatch["trim_boundary"] is None


@pytest.mark.asyncio
async def test_sse_still_persists_tool_calls_on_the_assistant_message(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tool-usage analytics reads `tool_calls` off the stored assistant message."""
    await _approve_site(db_repos, test_site["id"])

    async def _fake_build_system_prompt(
        self: ChatAgent,
        query: str,
        page_context: dict | None = None,
        repos: object = None,
        visitor_id: str | None = None,
        conversation_summary: str | None = None,
    ) -> tuple[str, list[dict], bool]:
        self.last_citations = []
        self.last_tool_calls = [{"name": "lookup_order", "success": True}]
        return "system prompt", [], True

    monkeypatch.setattr(ChatAgent, "_build_system_prompt", _fake_build_system_prompt)

    events = await _run_core_stream(test_site["token"], ChatSSERequest(message="where is my order?"), db_repos)

    session_id = json.loads([e for e in events if e.get("event") == "done"][-1]["data"])["session_id"]
    stored = await db_repos.chat_sessions.get_by_id(session_id)
    assert stored["messages"][-1]["tool_calls"] == [{"name": "lookup_order", "success": True}]


def _mock_request(path_params=None, authorization=None, query_site_token=None, ip="1.2.3.4"):
    """Build a MagicMock standing in for a starlette Request.

    Explicitly sets `headers` and `query_params` to plain dicts (rather than
    leaving them as auto-vivified MagicMock attributes) so `.get(...)` on an
    absent key returns a real `None` instead of a truthy child mock — the
    latter would make `site_token_key` think a token was present when the
    test intends there to be none.
    """
    from unittest.mock import MagicMock

    req = MagicMock()
    req.path_params = path_params or {}
    req.headers = {"authorization": authorization} if authorization else {}
    req.query_params = {"site_token": query_site_token} if query_site_token else {}
    req.client = MagicMock(host=ip)
    return req


@pytest.mark.asyncio
async def test_site_token_key_isolates_tenants():
    """site_token_key returns `site:<token>` so tenants never share buckets.

    This is a unit-level assertion of the key_func contract — the integration
    behaviour (429 after N requests) is exercised by slowapi's own test suite.
    Duplicating it here in a full ASGI test proved flaky under httpx's async
    transport; the critical invariant is that two different site tokens
    produce different keys.
    """
    from utils.rate_limit import site_token_key

    req_a = _mock_request(path_params={"site_token": "token-a"})
    req_b = _mock_request(path_params={"site_token": "token-b"})
    req_none = _mock_request()

    assert site_token_key(req_a) == "site:token-a"
    assert site_token_key(req_b) == "site:token-b"
    # Distinct buckets per token.
    assert site_token_key(req_a) != site_token_key(req_b)
    # No path param, header, or query token → degrade to IP.
    assert site_token_key(req_none) == "1.2.3.4"


@pytest.mark.asyncio
async def test_site_token_key_resolves_from_authorization_header():
    """A route with no `site_token` path param (e.g. the feedback endpoint) must still
    bucket per tenant when the token is carried as `Authorization: Bearer <token>`."""
    from utils.rate_limit import site_token_key

    req = _mock_request(authorization="Bearer header-token")
    assert site_token_key(req) == "site:header-token"


@pytest.mark.asyncio
async def test_site_token_key_resolves_from_query_param():
    """The deprecated `?site_token=` query param must also key its own bucket."""
    from utils.rate_limit import site_token_key

    req = _mock_request(query_site_token="query-token")
    assert site_token_key(req) == "site:query-token"


@pytest.mark.asyncio
async def test_site_token_key_path_param_takes_precedence():
    """When a path param, a header, and a query param are all present (shouldn't happen on
    any real route, but the precedence must still be deterministic), the path param wins —
    this keeps `/api/chat/{site_token}/stream` behaving exactly as it does today."""
    from utils.rate_limit import site_token_key

    req = _mock_request(
        path_params={"site_token": "path-token"},
        authorization="Bearer header-token",
        query_site_token="query-token",
    )
    assert site_token_key(req) == "site:path-token"
