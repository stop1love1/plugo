"""Tests for configuration and settings."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_settings_defaults():
    """Settings should have sensible defaults."""
    from config import settings

    assert settings.llm_provider in ("claude", "openai", "gemini", "ollama", "lmstudio")
    assert settings.database_provider in ("sqlite", "mongodb")
    assert settings.backend_port == 8000
    assert settings.chroma_path is not None


def test_provider_factory_valid():
    """Factory should create known providers without error."""
    from providers.factory import get_all_providers

    providers = get_all_providers()
    assert len(providers) == 5

    provider_ids = [p["id"] for p in providers]
    assert "claude" in provider_ids
    assert "openai" in provider_ids
    assert "gemini" in provider_ids
    assert "ollama" in provider_ids
    assert "lmstudio" in provider_ids


def test_provider_factory_invalid():
    """Factory should raise ValueError for unknown provider."""
    import pytest

    from providers.factory import get_llm_provider

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_provider("nonexistent_provider")


def test_validate_settings_rejects_default_mongo_password_in_prod(monkeypatch):
    """In production, the docker-compose default MongoDB password must abort startup."""
    import pytest

    from config import settings, validate_settings

    monkeypatch.setenv("ENV", "production")
    monkeypatch.setattr(settings, "database_provider", "mongodb")
    monkeypatch.setattr(settings, "mongodb_url", "mongodb://root:plugo_dev_password@db:27017")
    with pytest.raises(RuntimeError, match="MongoDB is using the default"):
        validate_settings()
