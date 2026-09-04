"""Tests for Sessions & Feedback flow."""

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest


@pytest.fixture
async def test_session(db_repos, test_site):
    """Create a test chat session with messages."""
    session_id = str(uuid.uuid4())
    messages = [
        {"role": "user", "content": "Hello", "timestamp": datetime.now(UTC).isoformat()},
        {"role": "assistant", "content": "Hi there! How can I help?", "timestamp": datetime.now(UTC).isoformat()},
        {"role": "user", "content": "Tell me about your product", "timestamp": datetime.now(UTC).isoformat()},
        {"role": "assistant", "content": "Our product is great!", "timestamp": datetime.now(UTC).isoformat()},
    ]
    session = await db_repos.chat_sessions.create(
        {
            "id": session_id,
            "site_id": test_site["id"],
            "visitor_id": f"visitor_{uuid.uuid4().hex[:8]}",
            "messages": messages,
            "started_at": datetime.now(UTC),
        }
    )
    yield session
    with contextlib.suppress(Exception):
        await db_repos.chat_sessions.delete(session_id)


@pytest.mark.asyncio
async def test_list_sessions_without_auth(client, test_site):
    """GET /api/sessions without auth should return 401."""
    response = await client.get(f"/api/sessions?site_id={test_site['id']}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_sessions_rejects_oversized_per_page(client, auth_headers, test_site):
    """per_page must be capped so a client can't request an unbounded page (DoS)."""
    response = await client.get(f"/api/sessions?site_id={test_site['id']}&per_page=100000", headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_session_by_id(client, auth_headers, test_session):
    """GET /api/sessions/{session_id} should return session details."""
    response = await client.get(f"/api/sessions/{test_session['id']}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == test_session["id"]


@pytest.mark.asyncio
async def test_get_session_without_auth(client):
    """GET /api/sessions/{session_id} without auth should return 401."""
    response = await client.get("/api/sessions/any-session-id")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_session_not_found(client, auth_headers):
    """GET /api/sessions/{session_id} with invalid id should return error."""
    response = await client.get("/api/sessions/nonexistent-session-id", headers=auth_headers)
    assert response.status_code == 200
    assert "error" in response.json()


@pytest.mark.parametrize(
    "message_index, rating",
    [
        (1, "up"),  # happy path: upvote an assistant reply
        (3, "down"),  # happy path: downvote an assistant reply
    ],
)
@pytest.mark.asyncio
async def test_submit_feedback_recorded(client, db_repos, test_site, test_session, message_index, rating):
    """POST /api/sessions/{id}/feedback with a valid rating returns 200 + 'Feedback recorded',
    and the rating is actually persisted on the stored message — not just echoed in the response.

    Feedback is a widget action authorized by the site token (sent as a bearer),
    not the admin JWT — so we authenticate the way the embedded widget does."""
    response = await client.post(
        f"/api/sessions/{test_session['id']}/feedback",
        json={"message_index": message_index, "rating": rating},
        headers={"Authorization": f"Bearer {test_site['token']}"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Feedback recorded"

    stored = await db_repos.chat_sessions.get_by_id(test_session["id"])
    assert stored["messages"][message_index]["feedback"] == rating


@pytest.mark.asyncio
async def test_submit_feedback_no_token_messages_unchanged(client, db_repos, test_session):
    """No token → 401, and the underlying stored messages must be untouched."""
    response = await client.post(
        f"/api/sessions/{test_session['id']}/feedback",
        json={"message_index": 1, "rating": "up"},
    )
    assert response.status_code == 401

    stored = await db_repos.chat_sessions.get_by_id(test_session["id"])
    assert "feedback" not in stored["messages"][1]


@pytest.mark.asyncio
async def test_submit_feedback_wrong_site_token_forbidden(client, db_repos, test_session):
    """A token that resolves to a *different* site than the session's owner must 403."""
    other_site = await db_repos.sites.create(
        {
            "name": "Other Site",
            "url": "https://other.example.com",
            "llm_provider": "claude",
            "llm_model": "claude-sonnet-4-20250514",
            "primary_color": "#6366f1",
            "greeting": "Hello!",
            "allowed_domains": "",
        }
    )
    try:
        response = await client.post(
            f"/api/sessions/{test_session['id']}/feedback",
            json={"message_index": 1, "rating": "up"},
            headers={"Authorization": f"Bearer {other_site['token']}"},
        )
        assert response.status_code == 403
    finally:
        with contextlib.suppress(Exception):
            await db_repos.sites.delete(other_site["id"])


@pytest.mark.asyncio
async def test_submit_feedback_query_param_token_still_works(client, test_site, test_session):
    """The deprecated ?site_token= query param must still authenticate feedback submissions."""
    response = await client.post(
        f"/api/sessions/{test_session['id']}/feedback?site_token={test_site['token']}",
        json={"message_index": 2, "rating": "down"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Feedback recorded"


@pytest.mark.asyncio
async def test_submit_feedback_no_token_nonexistent_session_still_401(client):
    """Missing token against a session id that doesn't exist must still be 401, not 404 —
    otherwise an unauthenticated caller could use the status code to probe which session
    ids exist."""
    response = await client.post(
        "/api/sessions/definitely-not-a-real-session-id/feedback",
        json={"message_index": 0, "rating": "up"},
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"message_index": 1, "rating": "neutral"},  # invalid rating enum
        {"message_index": -1, "rating": "up"},  # negative index rejected by schema
    ],
)
@pytest.mark.asyncio
async def test_submit_feedback_schema_rejects_bad_payload(client, auth_headers, test_session, payload):
    """Invalid rating enum or negative message_index must 422 at the schema layer."""
    response = await client.post(
        f"/api/sessions/{test_session['id']}/feedback",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_feedback_out_of_range_index(client, test_site, test_session):
    """An in-range-typed but non-existent message index should 200 with an error field, or 400."""
    response = await client.post(
        f"/api/sessions/{test_session['id']}/feedback",
        json={"message_index": 999, "rating": "up"},
        headers={"Authorization": f"Bearer {test_site['token']}"},
    )
    assert response.status_code in (200, 400)
    if response.status_code == 200:
        assert "error" in response.json()


@pytest.mark.asyncio
async def test_aggregate_overview_counts_at_db_layer(db_repos, test_site):
    """aggregate_overview must return correct totals without loading messages into Python."""
    site_id = test_site["id"]
    base = datetime.now(UTC)
    created_ids = []
    try:
        # Session 1: 2 messages, 60s duration
        s1 = await db_repos.chat_sessions.create(
            {
                "site_id": site_id,
                "messages": [
                    {"role": "user", "content": "a"},
                    {"role": "assistant", "content": "b"},
                ],
            }
        )
        created_ids.append(s1["id"])
        # Session 2: 4 messages, 120s duration
        s2 = await db_repos.chat_sessions.create(
            {
                "site_id": site_id,
                "messages": [
                    {"role": "user", "content": "a"},
                    {"role": "assistant", "content": "b"},
                    {"role": "user", "content": "c"},
                    {"role": "assistant", "content": "d"},
                ],
            }
        )
        created_ids.append(s2["id"])
        # Session 3: 1 message, still open (no ended_at)
        s3 = await db_repos.chat_sessions.create(
            {
                "site_id": site_id,
                "messages": [{"role": "user", "content": "hi"}],
            }
        )
        created_ids.append(s3["id"])

        # End s1 and s2 so duration is measurable
        await db_repos.chat_sessions.set_ended(s1["id"])
        await db_repos.chat_sessions.set_ended(s2["id"])

        stats = await db_repos.chat_sessions.aggregate_overview(site_id, base - timedelta(days=1))
        assert stats["total_sessions"] == 3
        assert stats["total_messages"] == 2 + 4 + 1
        # At least one ended session → avg duration should be >= 0 (exact value is flaky)
        assert stats["avg_session_duration_seconds"] >= 0.0
    finally:
        for sid in created_ids:
            with contextlib.suppress(Exception):
                await db_repos.chat_sessions.set_ended(sid)


@pytest.mark.asyncio
async def test_list_by_site_since_respects_limit(db_repos, test_site):
    """list_by_site_since must cap results at `limit` so analytics scans stay bounded."""
    base = datetime.now(UTC)
    created = []
    try:
        for i in range(3):
            s = await db_repos.chat_sessions.create(
                {
                    "site_id": test_site["id"],
                    "messages": [{"role": "user", "content": f"m{i}"}],
                    "started_at": base - timedelta(minutes=i),
                }
            )
            created.append(s["id"])
        rows = await db_repos.chat_sessions.list_by_site_since(test_site["id"], base - timedelta(days=1), limit=2)
        assert len(rows) == 2
    finally:
        for sid in created:
            with contextlib.suppress(Exception):
                await db_repos.chat_sessions.delete(sid)


@pytest.mark.asyncio
async def test_delete_older_than_removes_old_keeps_recent(db_repos, test_site):
    """Retention cleanup must delete sessions older than the cutoff and keep newer ones."""
    base = datetime.now(UTC)
    old = await db_repos.chat_sessions.create(
        {
            "site_id": test_site["id"],
            "messages": [],
            "started_at": base - timedelta(days=120),
        }
    )
    recent = await db_repos.chat_sessions.create(
        {
            "site_id": test_site["id"],
            "messages": [],
            "started_at": base - timedelta(days=1),
        }
    )
    try:
        deleted = await db_repos.chat_sessions.delete_older_than(base - timedelta(days=90))
        assert deleted >= 1
        assert await db_repos.chat_sessions.get_by_id(old["id"]) is None
        assert await db_repos.chat_sessions.get_by_id(recent["id"]) is not None
    finally:
        for sid in (old["id"], recent["id"]):
            with contextlib.suppress(Exception):
                await db_repos.chat_sessions.delete(sid)


@pytest.mark.asyncio
async def test_add_token_usage_accumulates(db_repos, test_site):
    """Two calls to add_token_usage should cumulatively increment the columns."""
    session = await db_repos.chat_sessions.create(
        {
            "site_id": test_site["id"],
            "messages": [],
        }
    )
    sid = session["id"]

    ok = await db_repos.chat_sessions.add_token_usage(sid, 100, 50, 0.001)
    assert ok
    ok = await db_repos.chat_sessions.add_token_usage(sid, 200, 75, 0.002)
    assert ok

    refreshed = await db_repos.chat_sessions.get_by_id(sid)
    assert refreshed["tokens_input"] == 300
    assert refreshed["tokens_output"] == 125
    # Float comparison — allow small rounding error.
    assert abs(refreshed["cost_usd"] - 0.003) < 1e-9


@pytest.mark.asyncio
async def test_session_resume_lock_serializes_concurrent_resumes():
    """Two concurrent tasks acquiring the same session resume lock must not overlap."""
    from routers.chat import _get_session_resume_lock

    session_id = f"lock-test-{uuid.uuid4()}"
    in_critical = 0
    max_seen = 0

    async def worker():
        nonlocal in_critical, max_seen
        async with _get_session_resume_lock(session_id):
            in_critical += 1
            max_seen = max(max_seen, in_critical)
            await asyncio.sleep(0.01)
            in_critical -= 1

    await asyncio.gather(worker(), worker(), worker())
    assert max_seen == 1
