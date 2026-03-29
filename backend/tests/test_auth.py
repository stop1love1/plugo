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


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    """POST /api/auth/login with wrong password should return 401."""
    response = await client.post("/api/auth/login", json={
        "username": "plugo",
        "password": "wrongpassword",
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


@pytest.mark.asyncio
async def test_login_wrong_username(client):
    """POST /api/auth/login with wrong username should return 401."""
    response = await client.post("/api/auth/login", json={
        "username": "nonexistentuser",
        "password": "pluginme",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_with_valid_token(client, auth_headers):
    """GET /api/auth/me with valid token should return user info."""
    response = await client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "user_id" in data
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_get_me_without_token(client):
    """GET /api/auth/me without token should return 401."""
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_with_invalid_token(client):
    """GET /api/auth/me with invalid token should return 401."""
    response = await client.get("/api/auth/me", headers={
        "Authorization": "Bearer invalid-token-here",
    })
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
    from auth import create_access_token, decode_access_token
    from fastapi import HTTPException

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
