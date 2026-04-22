"""Tests for Sites CRUD flow and the per-site origin validator."""

import pytest
from utils.cors import validate_site_origin


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
    # Fresh sites must not be auto-approved — approval is an explicit admin action.
    assert data["is_approved"] is False

    # Cleanup
    await client.delete(f"/api/sites/{data['id']}", headers=auth_headers)


@pytest.mark.parametrize("overrides", [
    {"llm_provider": "invalid_provider"},
    {"primary_color": "not-a-color"},
    {"name": ""},
])
@pytest.mark.asyncio
async def test_create_site_rejects_invalid_payload(client, auth_headers, overrides):
    """POST /api/sites with invalid provider / color / empty name should 422."""
    payload = {"name": "Bad Site", "url": "https://example.com", **overrides}
    response = await client.post("/api/sites", json=payload, headers=auth_headers)
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
async def test_get_site_by_id(client, auth_headers, test_site):
    """GET /api/sites/{site_id} should return site details."""
    response = await client.get(f"/api/sites/{test_site['id']}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == test_site["id"]
    assert data["name"] == test_site["name"]


@pytest.mark.asyncio
async def test_get_site_not_found(client, auth_headers):
    """GET /api/sites/{site_id} with invalid id should return 404."""
    response = await client.get("/api/sites/nonexistent-id", headers=auth_headers)
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
async def test_update_site_not_found(client, auth_headers):
    """PUT /api/sites/{site_id} with invalid id should return 404."""
    response = await client.put("/api/sites/nonexistent-id", json={
        "name": "Ghost Site",
    }, headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_site_rejects_non_working_model(client, auth_headers, test_site, monkeypatch):
    """PUT /api/sites/{site_id} should reject model configs that fail verification."""
    async def fake_get_llm_provider(provider: str | None = None, model: str | None = None):
        raise AssertionError("This helper should not be awaited")

    class BrokenProvider:
        async def chat(self, messages, system_prompt="", tools=None, temperature=0.7):
            raise RuntimeError("Model check failed")

    monkeypatch.setattr("providers.factory.get_llm_provider", lambda provider=None, model=None: BrokenProvider())

    response = await client.put(
        f"/api/sites/{test_site['id']}",
        json={"llm_provider": "openai", "llm_model": "bad-model"},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "bad-model" in response.json()["detail"]


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
    response = await client.get(f"/api/sites/{site['id']}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_site_not_found(client, auth_headers):
    """DELETE /api/sites/{site_id} with invalid id should return 404."""
    response = await client.delete("/api/sites/nonexistent-id", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.parametrize("method, path", [
    ("POST", "/api/sites"),
    ("GET", "/api/sites"),
    ("PUT", "/api/sites/any-id"),
])
@pytest.mark.asyncio
async def test_sites_endpoints_require_auth(client, method, path):
    """All admin site endpoints must reject unauthenticated requests with 401."""
    response = await client.request(method, path, json={"name": "x", "url": "https://x.com"})
    assert response.status_code == 401


# --- Approval flow ---
# (is_approved=False default is asserted by test_create_site above.)


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


# --- validate_site_origin (per-site origin gate for widget routes) ---


@pytest.mark.parametrize(
    "site, origin, expected",
    [
        # Empty allowed_domains → permissive (legacy behaviour).
        ({"allowed_domains": ""}, "https://evil.com", True),
        # Exact host match.
        ({"allowed_domains": "example.com"}, "https://example.com", True),
        # Subdomain match (deep + shallow both allowed).
        ({"allowed_domains": "example.com"}, "https://sub.example.com", True),
        # Non-match: sibling / substring domains must be rejected.
        ({"allowed_domains": "example.com"}, "https://evilexample.com", False),
        # Configured allowlist but no Origin header → deny.
        ({"allowed_domains": "example.com"}, None, False),
        # Malformed origin (no hostname) → deny.
        ({"allowed_domains": "example.com"}, "not-a-url", False),
        # `Origin: null` (sandboxed iframes, file://) with a configured
        # allowlist → deny. This is a deliberate security contract: opaque
        # origins cannot be attributed to a tenant, so they must not pass.
        ({"allowed_domains": "example.com"}, "null", False),
        # Same `Origin: null` with an EMPTY allowlist → allow (permissive
        # dev path; the contract only tightens once a site opts in).
        ({"allowed_domains": ""}, "null", True),
    ],
)
def test_validate_site_origin(site, origin, expected):
    assert validate_site_origin(site, origin) is expected


def test_validate_site_origin_none_site_is_permissive():
    # Defensive: if the caller passes None (site lookup returned None and
    # they forgot to 404 first), don't raise.
    assert validate_site_origin(None, "https://anywhere.com") is True
