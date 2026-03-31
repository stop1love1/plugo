"""Crawl API behavior — settings vs toggle must not surprise users."""

import pytest


@pytest.mark.asyncio
async def test_update_crawl_settings_does_not_create_job(client, auth_headers, test_site):
    """Changing auto_interval via PUT /settings must not start a crawl or add a job."""
    site_id = test_site["id"]
    jobs_before = await client.get(f"/api/crawl/jobs/{site_id}", headers=auth_headers)
    assert jobs_before.status_code == 200
    n_before = len(jobs_before.json())

    status_before = await client.get(f"/api/crawl/status/{site_id}", headers=auth_headers)
    assert status_before.status_code == 200
    assert status_before.json().get("crawl_status") == "idle"

    resp = await client.put(
        f"/api/crawl/settings/{site_id}",
        json={"auto_interval": 24},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    jobs_after = await client.get(f"/api/crawl/jobs/{site_id}", headers=auth_headers)
    assert jobs_after.status_code == 200
    assert len(jobs_after.json()) == n_before

    status_after = await client.get(f"/api/crawl/status/{site_id}", headers=auth_headers)
    assert status_after.status_code == 200
    assert status_after.json().get("crawl_status") == "idle"
