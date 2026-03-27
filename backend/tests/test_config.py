"""Tests for configuration and settings."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_settings_defaults():
    """Settings should have sensible defaults."""
    from config import settings

    assert settings.llm_provider in ("claude", "openai", "gemini", "ollama")
    assert settings.database_provider in ("sqlite", "mongodb")
    assert settings.backend_port == 8000
    assert settings.chroma_path is not None


def test_provider_factory_valid():
    """Factory should create known providers without error."""
    from providers.factory import get_all_providers

    providers = get_all_providers()
    assert len(providers) == 4

    provider_ids = [p["id"] for p in providers]
    assert "claude" in provider_ids
    assert "openai" in provider_ids
    assert "gemini" in provider_ids
    assert "ollama" in provider_ids


def test_provider_factory_invalid():
    """Factory should raise ValueError for unknown provider."""
    import pytest
    from providers.factory import get_llm_provider

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_provider("nonexistent_provider")
