"""Tests for the audit log listing endpoint."""

import pytest


@pytest.mark.asyncio
async def test_list_audit_logs_requires_auth(client):
    """GET /api/audit without a token must 401."""
    response = await client.get("/api/audit")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_audit_logs_returns_logs(client, auth_headers):
    """GET /api/audit with a valid token returns a paginated logs payload."""
    response = await client.get("/api/audit", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert "logs" in body


@pytest.mark.asyncio
async def test_list_audit_logs_rejects_oversized_per_page(client, auth_headers):
    """per_page must be capped so a client can't request an unbounded page (DoS)."""
    response = await client.get("/api/audit?per_page=100000", headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_audit_logs_filter_by_action(client, auth_headers, db_repos):
    """The ?action= filter must restrict results to that action only."""
    await db_repos.audit_logs.create(
        {
            "user_id": "plugo",
            "username": "plugo",
            "action": "create",
            "resource_type": "site",
            "resource_id": "flt-1",
            "details": "{}",
        }
    )
    await db_repos.audit_logs.create(
        {
            "user_id": "plugo",
            "username": "plugo",
            "action": "delete",
            "resource_type": "site",
            "resource_id": "flt-2",
            "details": "{}",
        }
    )
    r = await client.get("/api/audit?action=create", headers=auth_headers)
    assert r.status_code == 200
    logs = r.json()["logs"]
    assert logs, "expected at least one create log"
    assert all(log["action"] == "create" for log in logs)


@pytest.mark.asyncio
async def test_list_audit_logs_filter_by_resource_type(client, auth_headers, db_repos):
    """The ?resource_type= filter must restrict results to that resource type."""
    await db_repos.audit_logs.create(
        {
            "user_id": "plugo",
            "username": "plugo",
            "action": "save",
            "resource_type": "llm_key",
            "resource_id": "openai",
            "details": "{}",
        }
    )
    r = await client.get("/api/audit?resource_type=llm_key", headers=auth_headers)
    assert r.status_code == 200
    logs = r.json()["logs"]
    assert logs
    assert all(log["resource_type"] == "llm_key" for log in logs)
