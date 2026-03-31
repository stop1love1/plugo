"""Tests for model provider status reporting."""

import pytest


@pytest.mark.asyncio
async def test_models_providers_reports_invalid_key_status(client, auth_headers, monkeypatch):
    """GET /api/models/providers should distinguish invalid keys from working keys."""

    monkeypatch.setattr(
        "routers.models.get_all_providers",
        lambda: [
            {
                "id": "openai",
                "name": "OpenAI",
                "models": [{"id": "gpt-4o", "name": "GPT-4o"}],
                "requires_key": True,
                "has_key": True,
            }
        ],
    )

    async def fake_status(provider_id: str, requires_key: bool, has_key: bool):
        assert provider_id == "openai"
        assert requires_key is True
        assert has_key is True
        return "invalid"

    monkeypatch.setattr("routers.models.get_provider_key_status", fake_status)

    response = await client.get("/api/models/providers", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data[0]["has_key"] is True
    assert data[0]["key_status"] == "invalid"
