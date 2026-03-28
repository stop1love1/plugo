"""Tests for Users management flow (admin only)."""

import pytest


@pytest.mark.asyncio
async def test_list_users_as_admin(client, auth_headers):
    """GET /api/users as admin should return user list."""
    response = await client.get("/api/users", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1  # At least the test user


@pytest.mark.asyncio
async def test_list_users_without_auth(client):
    """GET /api/users without auth should return 401."""
    response = await client.get("/api/users")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_users_as_viewer(client, db_repos):
    """GET /api/users as viewer should return 403."""
    from auth import hash_password, create_access_token
    import uuid

    user = await db_repos.users.create({
        "id": str(uuid.uuid4()),
        "username": f"viewer_{uuid.uuid4().hex[:8]}",
        "password_hash": hash_password("viewerpass123"),
        "role": "viewer",
    })

    token = create_access_token(subject=user["id"], role="viewer")
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get("/api/users", headers=headers)
    assert response.status_code == 403

    # Cleanup
    await db_repos.users.delete(user["id"])


@pytest.mark.asyncio
async def test_create_user(client, auth_headers):
    """POST /api/users should create a new user."""
    import uuid
    username = f"newuser_{uuid.uuid4().hex[:8]}"
    response = await client.post("/api/users", json={
        "username": username,
        "password": "newpassword123",
        "role": "viewer",
    }, headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["username"] == username
    assert data["role"] == "viewer"
    assert "id" in data

    # Cleanup
    await client.delete(f"/api/users/{data['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_create_user_duplicate_username(client, auth_headers, test_user):
    """POST /api/users with existing username should return 400."""
    response = await client.post("/api/users", json={
        "username": test_user["username"],
        "password": "anotherpass123",
        "role": "viewer",
    }, headers=auth_headers)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_user_short_password(client, auth_headers):
    """POST /api/users with short password should return 422."""
    response = await client.post("/api/users", json={
        "username": "shortpw_user",
        "password": "short",
        "role": "viewer",
    }, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_user_invalid_role(client, auth_headers):
    """POST /api/users with invalid role should return 422."""
    response = await client.post("/api/users", json={
        "username": "badrole_user",
        "password": "validpassword123",
        "role": "superadmin",
    }, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_user_role(client, auth_headers, db_repos):
    """PUT /api/users/{id}/role should update user role."""
    from auth import hash_password
    import uuid

    user = await db_repos.users.create({
        "id": str(uuid.uuid4()),
        "username": f"roletest_{uuid.uuid4().hex[:8]}",
        "password_hash": hash_password("testpass12345"),
        "role": "viewer",
    })

    response = await client.put(
        f"/api/users/{user['id']}/role",
        json={"role": "admin"},
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Cleanup
    await db_repos.users.delete(user["id"])


@pytest.mark.asyncio
async def test_update_user_role_not_found(client, auth_headers):
    """PUT /api/users/{id}/role with invalid id should return 404."""
    response = await client.put(
        "/api/users/nonexistent-id/role",
        json={"role": "admin"},
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_user(client, auth_headers, db_repos):
    """DELETE /api/users/{id} should delete the user."""
    from auth import hash_password
    import uuid

    user = await db_repos.users.create({
        "id": str(uuid.uuid4()),
        "username": f"todelete_{uuid.uuid4().hex[:8]}",
        "password_hash": hash_password("deletepass123"),
        "role": "viewer",
    })

    response = await client.delete(
        f"/api/users/{user['id']}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["message"] == "User deleted"


@pytest.mark.asyncio
async def test_delete_user_not_found(client, auth_headers):
    """DELETE /api/users/{id} with invalid id should return 404."""
    response = await client.delete(
        "/api/users/nonexistent-id",
        headers=auth_headers,
    )
    assert response.status_code == 404
