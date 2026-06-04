"""Tests for authentication flow: env-based login, token validation."""

import pytest


@pytest.mark.asyncio
async def test_login_success(client):
    """POST /api/auth/login with valid env credentials should return a token."""
    response = await client.post(
        "/api/auth/login",
        json={
            "username": "plugo",
            "password": "test-admin-password",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "admin"
    assert data["username"] == "plugo"


@pytest.mark.parametrize(
    "username, password",
    [
        ("plugo", "wrongpassword"),  # correct user, wrong password
        ("nonexistentuser", "test-admin-password"),  # wrong user, correct password
    ],
)
@pytest.mark.asyncio
async def test_login_rejects_bad_credentials(client, username, password):
    """POST /api/auth/login must 401 for both wrong username and wrong password."""
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


@pytest.mark.asyncio
async def test_login_is_rate_limited(client):
    """Brute-force protection: rapid repeated logins from one IP must start
    returning 429 once the per-window limit (rate_limit_auth) is exceeded."""
    from main import limiter

    # Limiter is disabled by default in tests (see conftest autouse fixture);
    # turn it on locally to exercise the real per-window behaviour.
    limiter.enabled = True
    try:
        statuses = [
            (
                await client.post(
                    "/api/auth/login",
                    json={"username": "plugo", "password": "wrongpassword"},
                )
            ).status_code
            for _ in range(7)
        ]
    finally:
        limiter.enabled = False

    # Wrong creds → 401 until the limit kicks in, then 429 for the rest.
    assert 429 in statuses, f"expected a 429 after exceeding the login limit, got {statuses}"
    assert statuses.count(401) <= 5, f"too many attempts got through before limiting: {statuses}"


@pytest.mark.asyncio
async def test_get_me_with_valid_token(client, auth_headers):
    """GET /api/auth/me with valid token should return user info."""
    response = await client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "user_id" in data
    assert data["role"] == "admin"


@pytest.mark.parametrize(
    "headers",
    [
        None,  # missing Authorization header
        {"Authorization": "Bearer invalid-token-here"},  # malformed/invalid token
    ],
)
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

    assert verify_credentials("plugo", "test-admin-password") is True
    assert verify_credentials("plugo", "wrong") is False
    assert verify_credentials("wrong", "test-admin-password") is False


# --- httpOnly cookie auth + CSRF (Tier 2.1) ---


@pytest.mark.asyncio
async def test_login_sets_httponly_token_and_csrf_cookies(client):
    """Login must set an httpOnly session cookie (not JS-readable) plus a
    readable CSRF cookie for the double-submit pattern."""
    r = await client.post("/api/auth/login", json={"username": "plugo", "password": "test-admin-password"})
    assert r.status_code == 200
    set_cookies = " ".join(r.headers.get_list("set-cookie"))
    assert "plugo_token=" in set_cookies
    assert "httponly" in set_cookies.lower()  # session cookie is httpOnly
    assert "plugo_csrf=" in set_cookies


@pytest.mark.asyncio
async def test_me_authenticates_via_cookie_without_header(client):
    """After login, /me must work using only the httpOnly cookie (no Authorization header)."""
    await client.post("/api/auth/login", json={"username": "plugo", "password": "test-admin-password"})
    r = await client.get("/api/auth/me")  # cookie auto-sent by the client jar; no header
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_cookie_auth_mutation_blocked_without_csrf(client):
    """A state-changing request authenticated by cookie must be rejected (403)
    when the X-CSRF-Token header is missing (CSRF defence)."""
    await client.post("/api/auth/login", json={"username": "plugo", "password": "test-admin-password"})
    # No X-CSRF-Token header → blocked before reaching the handler.
    r = await client.post("/api/llm-keys", json={"provider": "openai", "api_key": "x", "label": ""})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_cookie_auth_mutation_allowed_with_csrf(client, monkeypatch):
    """The same request succeeds when the CSRF header echoes the CSRF cookie."""
    monkeypatch.setattr("providers.factory.refresh_key_cache", lambda: _noop_async())
    await client.post("/api/auth/login", json={"username": "plugo", "password": "test-admin-password"})
    csrf = client.cookies.get("plugo_csrf")
    assert csrf
    r = await client.post(
        "/api/llm-keys",
        json={"provider": "openai", "api_key": "sk-csrf-test", "label": ""},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    await client.delete("/api/llm-keys/openai", headers={"X-CSRF-Token": csrf})


@pytest.mark.asyncio
async def test_logout_clears_session_cookie(client):
    """Logout must expire the session cookie."""
    await client.post("/api/auth/login", json={"username": "plugo", "password": "test-admin-password"})
    csrf = client.cookies.get("plugo_csrf")
    r = await client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf or ""})
    assert r.status_code == 200
    set_cookies = " ".join(r.headers.get_list("set-cookie"))
    assert "plugo_token=" in set_cookies  # cleared via an expiring Set-Cookie


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
        log for log in audit.get("logs", []) if log.get("resource_type") == "llm_key" and log.get("action") == "save"
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
        log.get("resource_type") == "llm_key" and log.get("action") == "delete" and log.get("resource_id") == "gemini"
        for log in audit.get("logs", [])
    )


async def _noop_async():  # helper: coroutine-returning stub for refresh_key_cache
    return None
