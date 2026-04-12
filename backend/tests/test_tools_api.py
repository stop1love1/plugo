"""Tests for Tools CRUD flow."""

import contextlib

import pytest


@pytest.fixture
async def test_tool(db_repos, test_site):
    """Create a test tool."""
    tool = await db_repos.tools.create({
        "site_id": test_site["id"],
        "name": "Weather API",
        "description": "Get current weather for a location",
        "method": "GET",
        "url": "https://api.weather.com/current",
        "params_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"},
            },
        },
        "headers": {},
        "auth_type": "bearer",
        "auth_value": "test-api-key",
    })
    yield tool
    with contextlib.suppress(Exception):
        await db_repos.tools.delete(tool["id"])


@pytest.mark.asyncio
async def test_list_tools(client, auth_headers, test_site, test_tool):
    """GET /api/tools should return tools for a site."""
    response = await client.get(f"/api/tools?site_id={test_site['id']}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert any(t["id"] == test_tool["id"] for t in data)


@pytest.mark.asyncio
async def test_create_tool(client, auth_headers, test_site):
    """POST /api/tools should create a new tool."""
    response = await client.post("/api/tools", headers=auth_headers, json={
        "site_id": test_site["id"],
        "name": "Test Tool",
        "description": "A test tool",
        "method": "POST",
        "url": "https://api.example.com/action",
        "params_schema": {},
        "headers": {"Content-Type": "application/json"},
    })
    assert response.status_code == 200

    data = response.json()
    assert "id" in data
    assert data["message"] == "Tool created"

    # Cleanup
    await client.delete(f"/api/tools/{data['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_update_tool(client, auth_headers, test_tool):
    """PUT /api/tools/{tool_id} should update tool fields."""
    response = await client.put(f"/api/tools/{test_tool['id']}", headers=auth_headers, json={
        "name": "Updated Weather API",
        "description": "Updated description",
    })
    assert response.status_code == 200
    assert response.json()["message"] == "Tool updated"


@pytest.mark.asyncio
async def test_update_tool_not_found(client, auth_headers):
    """PUT /api/tools/{tool_id} with invalid id should return 404."""
    response = await client.put("/api/tools/nonexistent-id", headers=auth_headers, json={
        "name": "Ghost Tool",
    })
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_tool(client, auth_headers, db_repos, test_site):
    """DELETE /api/tools/{tool_id} should delete the tool."""
    tool = await db_repos.tools.create({
        "site_id": test_site["id"],
        "name": "To Delete",
        "description": "Delete me",
        "method": "GET",
        "url": "https://example.com",
    })

    response = await client.delete(f"/api/tools/{tool['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Tool deleted"


@pytest.mark.asyncio
async def test_delete_tool_not_found(client, auth_headers):
    """DELETE /api/tools/{tool_id} with invalid id should return 404."""
    response = await client.delete("/api/tools/nonexistent-id", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_tool_with_auth_config(client, auth_headers, test_site):
    """POST /api/tools with auth config should store auth settings."""
    response = await client.post("/api/tools", headers=auth_headers, json={
        "site_id": test_site["id"],
        "name": "Authenticated Tool",
        "description": "A tool with API key auth",
        "method": "GET",
        "url": "https://api.example.com/secure",
        "auth_type": "api_key",
        "auth_value": "sk-test-key-123",
    })
    assert response.status_code == 200
    tool_id = response.json()["id"]

    # Verify tool was created with auth settings
    tools = await client.get(f"/api/tools?site_id={test_site['id']}", headers=auth_headers)
    found = [t for t in tools.json() if t["id"] == tool_id]
    assert len(found) == 1
    assert found[0]["auth_type"] == "api_key"

    # Cleanup
    await client.delete(f"/api/tools/{tool_id}", headers=auth_headers)
