"""Tests for authentication flow: login, token validation, setup-status."""

import pytest


@pytest.mark.asyncio
async def test_setup_status_no_users(client, db_repos):
    """GET /api/auth/setup-status should reflect whether users exist."""
    response = await client.get("/api/auth/setup-status")
    assert response.status_code == 200
    data = response.json()
    assert "has_users" in data


@pytest.mark.asyncio
async def test_login_success(client, test_user):
    """POST /api/auth/login with valid credentials should return a token."""
    response = await client.post("/api/auth/login", json={
        "username": test_user["username"],
        "password": "testpassword123",
    })
    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "admin"
    assert data["username"] == test_user["username"]


@pytest.mark.asyncio
async def test_login_wrong_password(client, test_user):
    """POST /api/auth/login with wrong password should return 401."""
    response = await client.post("/api/auth/login", json={
        "username": test_user["username"],
        "password": "wrongpassword123",
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


@pytest.mark.asyncio
async def test_login_nonexistent_user(client):
    """POST /api/auth/login with unknown username should return 401."""
    response = await client.post("/api/auth/login", json={
        "username": "nonexistentuser",
        "password": "testpassword123",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_short_password_rejected(client):
    """POST /api/auth/login with password < 8 chars should return 422."""
    response = await client.post("/api/auth/login", json={
        "username": "testuser",
        "password": "short",
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_short_username_rejected(client):
    """POST /api/auth/login with username < 3 chars should return 422."""
    response = await client.post("/api/auth/login", json={
        "username": "ab",
        "password": "testpassword123",
    })
    assert response.status_code == 422


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
async def test_token_contains_correct_claims(test_user):
    """Token should contain correct sub and role claims."""
    from auth import create_access_token, decode_access_token

    token = create_access_token(subject=test_user["id"], role="admin")
    data = decode_access_token(token)

    assert data.sub == test_user["id"]
    assert data.role == "admin"


@pytest.mark.asyncio
async def test_expired_token_rejected():
    """Expired token should raise 401."""
    from datetime import timedelta
    from auth import create_access_token, decode_access_token
    from fastapi import HTTPException

    token = create_access_token(
        subject="test-user",
        role="admin",
        expires_delta=timedelta(seconds=-1),
    )

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_password_hash_verify():
    """Password hashing and verification should work correctly."""
    from auth import hash_password, verify_password

    plain = "my-secret-password"
    hashed = hash_password(plain)

    assert hashed != plain
    assert verify_password(plain, hashed) is True
    assert verify_password("wrong-password", hashed) is False
