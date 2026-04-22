"""Tests for authentication flow: env-based login, token validation."""

import pytest


@pytest.mark.asyncio
async def test_login_success(client):
    """POST /api/auth/login with valid env credentials should return a token."""
    response = await client.post("/api/auth/login", json={
        "username": "plugo",
        "password": "pluginme",
    })
    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "admin"
    assert data["username"] == "plugo"


@pytest.mark.parametrize("username, password", [
    ("plugo", "wrongpassword"),        # correct user, wrong password
    ("nonexistentuser", "pluginme"),   # wrong user, correct password
])
@pytest.mark.asyncio
async def test_login_rejects_bad_credentials(client, username, password):
    """POST /api/auth/login must 401 for both wrong username and wrong password."""
    response = await client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


@pytest.mark.asyncio
async def test_get_me_with_valid_token(client, auth_headers):
    """GET /api/auth/me with valid token should return user info."""
    response = await client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "user_id" in data
    assert data["role"] == "admin"


@pytest.mark.parametrize("headers", [
    None,  # missing Authorization header
    {"Authorization": "Bearer invalid-token-here"},  # malformed/invalid token
])
@pytest.mark.asyncio
async def test_get_me_rejects_missing_or_invalid_token(client, headers):
    """GET /api/auth/me must return 401 when no token or a bad token is provided."""
    response = await client.get("/api/auth/me", headers=headers or {})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_token_contains_correct_claims():
    """Token should contain correct sub and role claims."""
    from auth import create_access_token, decode_access_token

    token = create_access_token(subject="plugo", role="admin")
    data = decode_access_token(token)

    assert data.sub == "plugo"
    assert data.role == "admin"


@pytest.mark.asyncio
async def test_expired_token_rejected():
    """Expired token should raise 401."""
    from datetime import timedelta

    from fastapi import HTTPException

    from auth import create_access_token, decode_access_token

    token = create_access_token(
        subject="admin",
        role="admin",
        expires_delta=timedelta(seconds=-1),
    )

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_credentials():
    """verify_credentials should match env vars."""
    from auth import verify_credentials

    assert verify_credentials("plugo", "pluginme") is True
    assert verify_credentials("plugo", "wrong") is False
    assert verify_credentials("wrong", "pluginme") is False


# --- LLM key audit trail (C-5) ---


@pytest.mark.asyncio
async def test_save_llm_key_writes_audit_log(client, auth_headers, db_repos, monkeypatch):
    """POST /api/llm-keys must leave an audit row with action=save, key_last4 only."""
    # Avoid touching the real provider factory cache between tests.
    monkeypatch.setattr("providers.factory.refresh_key_cache", lambda: _noop_async())

    raw_key = "sk-abc-TEST-KEY-1234"
    r = await client.post(
        "/api/llm-keys",
        json={"provider": "openai", "api_key": raw_key, "label": "primary"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text

    audit = await db_repos.audit_logs.list_by_site(page=1, per_page=50)
    llm_logs = [
        log for log in audit.get("logs", [])
        if log.get("resource_type") == "llm_key" and log.get("action") == "save"
    ]
    assert llm_logs, "save audit log not found"
    # Full key MUST NOT appear in details — only last 4 chars.
    row = llm_logs[0]
    details = row["details"] if isinstance(row["details"], str) else str(row["details"])
    assert raw_key not in details
    assert raw_key[-4:] in details

    # Cleanup.
    await client.delete("/api/llm-keys/openai", headers=auth_headers)


@pytest.mark.asyncio
async def test_delete_llm_key_writes_audit_log(client, auth_headers, db_repos, monkeypatch):
    monkeypatch.setattr("providers.factory.refresh_key_cache", lambda: _noop_async())

    # Create a key first.
    await client.post(
        "/api/llm-keys",
        json={"provider": "gemini", "api_key": "g-key-zzzz", "label": ""},
        headers=auth_headers,
    )
    r = await client.delete("/api/llm-keys/gemini", headers=auth_headers)
    assert r.status_code == 200

    audit = await db_repos.audit_logs.list_by_site(page=1, per_page=50)
    assert any(
        log.get("resource_type") == "llm_key"
        and log.get("action") == "delete"
        and log.get("resource_id") == "gemini"
        for log in audit.get("logs", [])
    )


async def _noop_async():  # helper: coroutine-returning stub for refresh_key_cache
    return None
