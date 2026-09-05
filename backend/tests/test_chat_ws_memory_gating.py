"""The WebSocket transport must gate session-end memory extraction on visitor-id
addressability, the same way `chat_sse.py` gates its cadence-based extraction.

Both transports mint a throwaway `uuid4()` visitor id when the client supplies none. On
WS that id lives only for the socket's lifetime: no later connection can present it back,
so `visitor_memories` rows written under it are unreachable forever, and the extraction
that wrote them is still a billed LLM round trip. `visitor_is_addressable` in
`routers/chat.py` mirrors `chat_sse.py`'s flag of the same name, computed the same way:
`bool(sanitized)` before the uuid4() fallback runs.

Summarization is keyed by session, not visitor, so it must keep running for anonymous
connections — only the extraction dispatch is gated.

These tests also pin the removal of the dead `if not visitor_id: visitor_id =
existing_session.get(...)` resume branch: a resumed connection's addressability (and the
visitor_id used for the turn) comes from what *this* connection's client supplied, never
from whatever a prior connection happened to store on the session row.
"""

import asyncio

import pytest

from agent.core import ChatAgent
from repositories import Repositories, create_repos
from routers.chat import _background_tasks, _run_websocket_chat
from tests.conftest import _FakeWebSocket, _StubProvider


def _history(turns: int) -> list[dict]:
    history: list[dict] = []
    for i in range(turns):
        history.append({"role": "user", "content": f"question {i}", "timestamp": "2026-01-01T00:00:00Z"})
        history.append({"role": "assistant", "content": f"answer {i}", "timestamp": "2026-01-01T00:00:01Z"})
    return history


async def _seed_session(db_repos: Repositories, site_id: str, visitor_id: str, turns: int) -> str:
    """Create a session for `site_id` carrying `turns` stored visitor/assistant turns."""
    session = await db_repos.chat_sessions.create({"site_id": site_id, "visitor_id": visitor_id})
    history = _history(turns)
    if history:
        await db_repos.chat_sessions.update_messages(session["id"], history)
    return session["id"]


def _capture_background_helpers(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[dict]]:
    """Swap the two background helpers for recorders, leaving `_fire_and_forget` real."""
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
        calls["summarize"].append({"session_id": session_id, "messages": messages})

    monkeypatch.setattr("routers.chat._extract_and_save_memories", _fake_extract)
    monkeypatch.setattr("routers.chat._maybe_summarize", _fake_summarize)
    return calls


async def _drain_background(baseline: set[asyncio.Task], timeout: float = 10.0) -> None:
    """Await the `_fire_and_forget` tasks started since `baseline`."""
    pending = [task for task in _background_tasks if task not in baseline]
    if not pending:
        return
    _, still_running = await asyncio.wait(pending, timeout=timeout)
    if still_running:
        raise AssertionError(f"background tasks still running after {timeout}s: {still_running}")


def _patch_stub_agent(monkeypatch: pytest.MonkeyPatch) -> None:
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


async def _run_ws(test_site: dict, first_data: dict, frames: list[dict]) -> None:
    websocket = _FakeWebSocket(frames=frames)
    ws_repos = await create_repos()
    await _run_websocket_chat(
        websocket,
        ws_repos,
        {**test_site, "is_approved": True},
        test_site["token"],
        first_data=first_data,
    )


@pytest.mark.asyncio
async def test_ws_anonymous_resumed_session_skips_extraction_but_still_summarizes(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No client-supplied visitor id on the connection means no session-end extraction.

    The resumed session already has 18 stored messages under a *prior* connection's
    visitor id; this connection supplies none of its own. Summarization is keyed by the
    session, so the turn that crosses 20 must still dispatch it.
    """
    _patch_stub_agent(monkeypatch)
    calls = _capture_background_helpers(monkeypatch)

    session_id = await _seed_session(db_repos, test_site["id"], f"{test_site['id']}:prior-visitor", turns=9)
    baseline = set(_background_tasks)

    await _run_ws(
        test_site,
        first_data={"type": "init", "session_id": session_id},
        frames=[{"message": "final question"}],
    )
    await _drain_background(baseline)

    # 18 stored + this turn's pair = 20: crosses the summarization threshold.
    assert len(calls["summarize"]) == 1
    assert calls["summarize"][0]["session_id"] == session_id
    # But no visitor id was ever presented by this connection, so extraction is skipped
    # even though the session comfortably clears the >=4 message floor.
    assert calls["memories"] == []


@pytest.mark.asyncio
async def test_ws_client_supplied_visitor_id_still_extracts_at_session_end(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real, client-supplied visitor id must still get its extraction, as before."""
    _patch_stub_agent(monkeypatch)
    calls = _capture_background_helpers(monkeypatch)
    baseline = set(_background_tasks)

    await _run_ws(
        test_site,
        first_data={"visitor_id": "visitor-abc", "message": "question one"},
        frames=[{"message": "question two"}],
    )
    await _drain_background(baseline)

    # Two turns = 4 stored messages: exactly the session-end extraction floor.
    assert len(calls["memories"]) == 1
    extraction = calls["memories"][0]
    assert extraction["visitor_id"] == f"{test_site['id']}:visitor-abc"
    assert len(extraction["messages"]) == 4
    # Nowhere near the summarization threshold.
    assert calls["summarize"] == []


@pytest.mark.asyncio
async def test_ws_short_anonymous_session_skips_extraction(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Below the floor there is nothing worth extracting from regardless of addressability."""
    _patch_stub_agent(monkeypatch)
    calls = _capture_background_helpers(monkeypatch)
    baseline = set(_background_tasks)

    await _run_ws(test_site, first_data={"message": "just one question"}, frames=[])
    await _drain_background(baseline)

    assert calls["memories"] == []
    assert calls["summarize"] == []


@pytest.mark.asyncio
async def test_ws_resume_does_not_inherit_stored_visitor_id(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins the deletion of the dead resume branch.

    The session row already carries a real-looking visitor id from a prior connection.
    This connection resumes without supplying one of its own. If the dead
    `visitor_id = existing_session.get("visitor_id")` branch were revived, the resumed
    connection would silently inherit that stored id — indistinguishable from a
    client-supplied one at the `visitor_is_addressable` gate, and (per the SSE fix's
    established reasoning) potentially itself just a stored throwaway. This connection
    must use its own freshly-computed id instead, and extraction must stay gated off.
    """
    monkeypatch.setattr("agent.core.get_llm_provider", lambda *a, **k: _StubProvider())
    captured_visitor_ids: list[str | None] = []

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
        captured_visitor_ids.append(visitor_id)
        return "system prompt", [], True

    monkeypatch.setattr(ChatAgent, "_build_system_prompt", _fake_build_system_prompt)
    calls = _capture_background_helpers(monkeypatch)

    stored_visitor_id = f"{test_site['id']}:prior-visitor"
    session_id = await _seed_session(db_repos, test_site["id"], stored_visitor_id, turns=1)
    baseline = set(_background_tasks)

    await _run_ws(
        test_site,
        first_data={"type": "init", "session_id": session_id},
        frames=[{"message": "another question"}],
    )
    await _drain_background(baseline)

    assert len(captured_visitor_ids) == 1
    used_visitor_id = captured_visitor_ids[0]
    assert used_visitor_id is not None
    # Never the stored id from the prior connection.
    assert used_visitor_id != stored_visitor_id
    # Still scoped to the site, but with a freshly-minted suffix.
    assert used_visitor_id.startswith(f"{test_site['id']}:")
    assert used_visitor_id.split(":", 1)[1] != "prior-visitor"

    # 2 stored + this turn's pair = 4: clears the floor, but addressability stays false
    # because this connection never supplied its own visitor id.
    assert calls["memories"] == []
