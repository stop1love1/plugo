"""Tests for Sessions & Feedback flow."""

import uuid
from datetime import datetime, timezone

import pytest


@pytest.fixture
async def test_session(db_repos, test_site):
    """Create a test chat session with messages."""
    session_id = str(uuid.uuid4())
    messages = [
        {"role": "user", "content": "Hello", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": "Hi there! How can I help?", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "user", "content": "Tell me about your product", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": "Our product is great!", "timestamp": datetime.now(timezone.utc).isoformat()},
    ]
    session = await db_repos.chat_sessions.create({
        "id": session_id,
        "site_id": test_site["id"],
        "visitor_id": f"visitor_{uuid.uuid4().hex[:8]}",
        "messages": messages,
        "started_at": datetime.now(timezone.utc),
    })
    yield session
    try:
        await db_repos.chat_sessions.delete(session_id)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_list_sessions(client, auth_headers, test_site, test_session):
    """GET /api/sessions should return sessions for a site."""
    response = await client.get(f"/api/sessions?site_id={test_site['id']}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    if isinstance(data, dict):
        assert "sessions" in data or "items" in data
    else:
        assert isinstance(data, list)


@pytest.mark.asyncio
async def test_list_sessions_without_auth(client, test_site):
    """GET /api/sessions without auth should return 401."""
    response = await client.get(f"/api/sessions?site_id={test_site['id']}")
    assert response.status_code == 401


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


@pytest.mark.asyncio
async def test_submit_feedback_up(client, auth_headers, test_session):
    """POST /api/sessions/{id}/feedback with 'up' should record feedback."""
    response = await client.post(
        f"/api/sessions/{test_session['id']}/feedback",
        json={"message_index": 1, "rating": "up"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Feedback recorded"


@pytest.mark.asyncio
async def test_submit_feedback_down(client, auth_headers, test_session):
    """POST /api/sessions/{id}/feedback with 'down' should record feedback."""
    response = await client.post(
        f"/api/sessions/{test_session['id']}/feedback",
        json={"message_index": 3, "rating": "down"},
        headers=auth_headers,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_submit_feedback_invalid_rating(client, auth_headers, test_session):
    """POST /api/sessions/{id}/feedback with invalid rating should return 422."""
    response = await client.post(
        f"/api/sessions/{test_session['id']}/feedback",
        json={"message_index": 1, "rating": "neutral"},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_feedback_invalid_index(client, auth_headers, test_session):
    """POST /api/sessions/{id}/feedback with out-of-range index should return error."""
    response = await client.post(
        f"/api/sessions/{test_session['id']}/feedback",
        json={"message_index": 999, "rating": "up"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert "error" in response.json()


@pytest.mark.asyncio
async def test_submit_feedback_negative_index(client, auth_headers, test_session):
    """POST /api/sessions/{id}/feedback with negative index should return 422."""
    response = await client.post(
        f"/api/sessions/{test_session['id']}/feedback",
        json={"message_index": -1, "rating": "up"},
        headers=auth_headers,
    )
    assert response.status_code == 422
