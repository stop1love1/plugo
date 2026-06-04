"""Tests for health and root endpoints."""

import pytest


@pytest.mark.asyncio
async def test_root_endpoint(client):
    """GET / should return app info."""
    response = await client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Plugo"
    assert data["version"] == "1.0.0"
    assert "docs" in data


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """GET /health should return ok status."""
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert "database" in data


@pytest.mark.asyncio
async def test_response_has_request_id_header(client):
    """Every response must carry an X-Request-ID for log correlation."""
    response = await client.get("/health")
    assert response.headers.get("X-Request-ID")
