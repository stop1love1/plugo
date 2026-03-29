"""Tests for Sites CRUD flow."""

import pytest


@pytest.mark.asyncio
async def test_create_site(client, auth_headers):
    """POST /api/sites should create a new site."""
    response = await client.post("/api/sites", json={
        "name": "My Test Site",
        "url": "https://mysite.com",
    }, headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "My Test Site"
    assert data["url"] == "https://mysite.com"
    assert "id" in data
    assert "token" in data
    assert data["llm_provider"] == "claude"
    assert data["primary_color"] == "#6366f1"

    # Cleanup
    await client.delete(f"/api/sites/{data['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_create_site_without_auth(client):
    """POST /api/sites without auth should return 401."""
    response = await client.post("/api/sites", json={
        "name": "Unauthorized Site",
        "url": "https://example.com",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_site_invalid_provider(client, auth_headers):
    """POST /api/sites with invalid provider should return 422."""
    response = await client.post("/api/sites", json={
        "name": "Bad Provider Site",
        "url": "https://example.com",
        "llm_provider": "invalid_provider",
    }, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_site_invalid_color(client, auth_headers):
    """POST /api/sites with invalid color should return 422."""
    response = await client.post("/api/sites", json={
        "name": "Bad Color Site",
        "url": "https://example.com",
        "primary_color": "not-a-color",
    }, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_sites(client, auth_headers, test_site):
    """GET /api/sites should return list of sites."""
    response = await client.get("/api/sites", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert any(s["id"] == test_site["id"] for s in data)


@pytest.mark.asyncio
async def test_list_sites_without_auth(client):
    """GET /api/sites without auth should return 401."""
    response = await client.get("/api/sites")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_site_by_id(client, test_site):
    """GET /api/sites/{site_id} should return site details."""
    response = await client.get(f"/api/sites/{test_site['id']}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == test_site["id"]
    assert data["name"] == test_site["name"]


@pytest.mark.asyncio
async def test_get_site_not_found(client):
    """GET /api/sites/{site_id} with invalid id should return 404."""
    response = await client.get("/api/sites/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_site(client, auth_headers, test_site):
    """PUT /api/sites/{site_id} should update site fields."""
    response = await client.put(f"/api/sites/{test_site['id']}", json={
        "name": "Updated Name",
        "primary_color": "#ff0000",
    }, headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["primary_color"] == "#ff0000"


@pytest.mark.asyncio
async def test_update_site_without_auth(client, test_site):
    """PUT /api/sites/{site_id} without auth should return 401."""
    response = await client.put(f"/api/sites/{test_site['id']}", json={
        "name": "Hacked Name",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_site_not_found(client, auth_headers):
    """PUT /api/sites/{site_id} with invalid id should return 404."""
    response = await client.put("/api/sites/nonexistent-id", json={
        "name": "Ghost Site",
    }, headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_site(client, auth_headers, db_repos):
    """DELETE /api/sites/{site_id} should delete the site."""
    # Create a site to delete
    site = await db_repos.sites.create({
        "name": "To Delete",
        "url": "https://delete.me",
    })

    response = await client.delete(f"/api/sites/{site['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Site deleted"

    # Verify it's gone
    response = await client.get(f"/api/sites/{site['id']}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_site_not_found(client, auth_headers):
    """DELETE /api/sites/{site_id} with invalid id should return 404."""
    response = await client.delete("/api/sites/nonexistent-id", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_providers(client):
    """GET /api/sites/providers/list should return available providers (public)."""
    response = await client.get("/api/sites/providers/list")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


@pytest.mark.asyncio
async def test_create_site_empty_name_rejected(client, auth_headers):
    """POST /api/sites with empty name should return 422."""
    response = await client.post("/api/sites", json={
        "name": "",
        "url": "https://example.com",
    }, headers=auth_headers)
    assert response.status_code == 422


# --- Approval flow ---


@pytest.mark.asyncio
async def test_new_site_is_not_approved_by_default(client, auth_headers):
    """POST /api/sites should create site with is_approved=False."""
    response = await client.post("/api/sites", json={
        "name": "Unapproved Site",
        "url": "https://unapproved.example.com",
    }, headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["is_approved"] is False

    # Cleanup
    await client.delete(f"/api/sites/{data['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_approve_site(client, auth_headers, test_site):
    """PUT /api/sites/{id}/approval should approve a site."""
    response = await client.put(
        f"/api/sites/{test_site['id']}/approval",
        json={"is_approved": True},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["is_approved"] is True


@pytest.mark.asyncio
async def test_revoke_site_approval(client, auth_headers, test_site):
    """PUT /api/sites/{id}/approval with False should revoke approval."""
    # First approve
    await client.put(
        f"/api/sites/{test_site['id']}/approval",
        json={"is_approved": True},
        headers=auth_headers,
    )
    # Then revoke
    response = await client.put(
        f"/api/sites/{test_site['id']}/approval",
        json={"is_approved": False},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["is_approved"] is False


@pytest.mark.asyncio
async def test_approve_site_not_found(client, auth_headers):
    """PUT /api/sites/{id}/approval with invalid id should return 404."""
    response = await client.put(
        "/api/sites/nonexistent-id/approval",
        json={"is_approved": True},
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_approve_site_viewer_forbidden(client):
    """PUT /api/sites/{id}/approval as viewer should return 403."""
    from auth import create_access_token

    token = create_access_token(subject="viewer_user", role="viewer")
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.put(
        "/api/sites/any-site-id/approval",
        json={"is_approved": True},
        headers=headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_demo_page_returns_html(client, test_site):
    """GET /demo/{site_token} should return HTML demo page."""
    response = await client.get(f"/demo/{test_site['token']}")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert test_site["name"] in response.text
    assert "PlugoConfig" in response.text


@pytest.mark.asyncio
async def test_demo_page_not_found(client):
    """GET /demo/{invalid_token} should return 404."""
    response = await client.get("/demo/nonexistent-token")
    assert response.status_code == 404
