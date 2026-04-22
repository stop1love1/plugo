"""Tests for the flows router (/api/flows).

Covers CRUD, step management, reordering, and the RAG-sync side effect
(mocked — the real embed provider is never hit).
"""

import pytest


@pytest.fixture(autouse=True)
def _mock_flow_rag(monkeypatch):
    """Flow CRUD writes to RAG on most mutations. Stub every path that would
    hit the embedding provider or ChromaDB so tests stay hermetic."""

    class _StubProvider:
        async def embed(self, contents):
            return [[0.0] * 3 for _ in contents]

    async def _noop_add(*a, **kw):
        return []

    async def _noop_delete(*a, **kw):
        return None

    monkeypatch.setattr("routers.flows.get_llm_provider", lambda *a, **k: _StubProvider())
    monkeypatch.setattr("routers.flows.rag_engine.add_chunks", _noop_add)
    monkeypatch.setattr("routers.flows.rag_engine.delete_chunks", _noop_delete)


async def _create_flow(client, auth_headers, site_id: str, name: str = "Onboarding") -> str:
    r = await client.post(
        "/api/flows",
        json={"site_id": site_id, "name": name, "description": "d"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_create_flow_and_list(client, auth_headers, test_site):
    flow_id = await _create_flow(client, auth_headers, test_site["id"])
    r = await client.get(
        f"/api/flows?site_id={test_site['id']}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    flows = r.json()
    assert any(f["id"] == flow_id for f in flows)
    # step_count is attached by the list endpoint.
    assert all("step_count" in f for f in flows)


@pytest.mark.asyncio
async def test_list_flows_requires_auth(client, test_site):
    r = await client.get(f"/api/flows?site_id={test_site['id']}")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_flow_requires_auth(client, test_site):
    r = await client.post(
        "/api/flows",
        json={"site_id": test_site["id"], "name": "x"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_flow_404(client, auth_headers):
    r = await client.get("/api/flows/nonexistent-id", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_update_flow(client, auth_headers, test_site):
    flow_id = await _create_flow(client, auth_headers, test_site["id"])
    r = await client.put(
        f"/api/flows/{flow_id}",
        json={"name": "Renamed"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["message"] == "Flow updated"


@pytest.mark.asyncio
async def test_update_flow_empty_body_400(client, auth_headers, test_site):
    flow_id = await _create_flow(client, auth_headers, test_site["id"])
    r = await client.put(
        f"/api/flows/{flow_id}",
        json={},
        headers=auth_headers,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_add_step_assigns_sequential_order(client, auth_headers, test_site):
    flow_id = await _create_flow(client, auth_headers, test_site["id"])
    r1 = await client.post(
        f"/api/flows/{flow_id}/steps",
        json={"title": "First"},
        headers=auth_headers,
    )
    r2 = await client.post(
        f"/api/flows/{flow_id}/steps",
        json={"title": "Second"},
        headers=auth_headers,
    )
    r3 = await client.post(
        f"/api/flows/{flow_id}/steps",
        json={"title": "Third"},
        headers=auth_headers,
    )
    assert r1.json()["step_order"] == 1
    assert r2.json()["step_order"] == 2
    assert r3.json()["step_order"] == 3


@pytest.mark.asyncio
async def test_reorder_steps_with_valid_ids(client, auth_headers, test_site):
    flow_id = await _create_flow(client, auth_headers, test_site["id"])
    ids = []
    for i in range(3):
        r = await client.post(
            f"/api/flows/{flow_id}/steps",
            json={"title": f"S{i}"},
            headers=auth_headers,
        )
        ids.append(r.json()["id"])

    # Reverse the order.
    r = await client.post(
        f"/api/flows/{flow_id}/reorder",
        json={"step_ids": list(reversed(ids))},
        headers=auth_headers,
    )
    assert r.status_code == 200

    # Confirm the order was actually reversed.
    flow = await client.get(f"/api/flows/{flow_id}", headers=auth_headers)
    steps = flow.json()["steps"]
    assert [s["id"] for s in steps] == list(reversed(ids))


@pytest.mark.asyncio
async def test_reorder_with_mismatched_ids_returns_400(client, auth_headers, test_site):
    """If the submitted id set doesn't match the flow's steps, reject."""
    flow_id = await _create_flow(client, auth_headers, test_site["id"])
    r = await client.post(
        f"/api/flows/{flow_id}/steps",
        json={"title": "Only"},
        headers=auth_headers,
    )
    real_id = r.json()["id"]
    # Extra bogus id → payload doesn't match.
    r = await client.post(
        f"/api/flows/{flow_id}/reorder",
        json={"step_ids": [real_id, "bogus-id"]},
        headers=auth_headers,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_delete_step_renumbers_remaining(client, auth_headers, test_site):
    flow_id = await _create_flow(client, auth_headers, test_site["id"])
    ids = []
    for i in range(3):
        r = await client.post(
            f"/api/flows/{flow_id}/steps",
            json={"title": f"S{i}"},
            headers=auth_headers,
        )
        ids.append(r.json()["id"])

    # Delete the first step.
    r = await client.delete(f"/api/flows/steps/{ids[0]}", headers=auth_headers)
    assert r.status_code == 200

    flow = await client.get(f"/api/flows/{flow_id}", headers=auth_headers)
    steps = flow.json()["steps"]
    assert len(steps) == 2
    # Renumbered 1..N from the remaining two.
    assert [s["step_order"] for s in steps] == [1, 2]


@pytest.mark.asyncio
async def test_update_step_not_found(client, auth_headers):
    r = await client.put(
        "/api/flows/steps/does-not-exist",
        json={"title": "x"},
        headers=auth_headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_flow_removes_it_from_list(client, auth_headers, test_site):
    flow_id = await _create_flow(client, auth_headers, test_site["id"])
    r = await client.delete(f"/api/flows/{flow_id}", headers=auth_headers)
    assert r.status_code == 200
    # List should no longer contain it.
    r = await client.get(
        f"/api/flows?site_id={test_site['id']}",
        headers=auth_headers,
    )
    assert not any(f["id"] == flow_id for f in r.json())


@pytest.mark.asyncio
async def test_delete_flow_not_found(client, auth_headers):
    r = await client.delete("/api/flows/nonexistent-id", headers=auth_headers)
    assert r.status_code == 404
