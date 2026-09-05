"""Tests for configuration and settings."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_settings_defaults() -> None:
    """Assert the loader's contract, not one particular operator's values.

    `config.json` is a committed, documented customization point for a self-hosted
    product, and the loader fix made it live in this suite for the first time. An
    assertion like `backend_port == 8000` therefore turns the most ordinary edit that
    file invites — setting a different port — into a red suite, from a test that was
    inert before and has nothing to say about ports. So: types and ranges here, and the
    two membership checks below only where the value really is constrained by code
    rather than by taste, each failing with a message that names the config key.
    """
    from config import settings
    from providers.factory import get_all_providers

    known_providers = {p["id"] for p in get_all_providers()}
    assert settings.llm_provider in known_providers, (
        f"config.json → llm.provider is {settings.llm_provider!r}, which "
        f"providers/factory.py cannot construct (it knows {sorted(known_providers)}). "
        "Derived from the factory rather than hard-coded, so adding a provider there "
        "is all it takes."
    )
    assert settings.database_provider in ("sqlite", "mongodb"), (
        f"config.json → database.provider is {settings.database_provider!r}; "
        "repositories/__init__.py branches on 'mongodb' and treats everything else as "
        "sqlite, so a typo here silently selects the wrong backend"
    )

    assert isinstance(settings.backend_port, int) and 1 <= settings.backend_port <= 65535, (
        f"config.json → server.backend_port is {settings.backend_port!r}, not a usable TCP port"
    )
    assert settings.chroma_path


def test_config_json_is_actually_loaded() -> None:
    """The loader must find and parse config.json.

    This is what the value assertions above used to pin by accident, and badly: they
    happened to match the shipped file, so they would have caught the loader being
    inert — but only while nobody edited it. `config.py`'s `.resolve()` is what makes
    the lookup work under the `tests/..` prefix conftest.py puts on `sys.path`; drop it
    and every setting silently reverts to its hard-coded default, which is exactly the
    state this branch found the suite in.
    """
    from config import _CONFIG_PATHS, _json_config

    assert _json_config, (
        f"config.json was not found — every setting is falling back to its hard-coded "
        f"default. Searched: {[str(p) for p in _CONFIG_PATHS]}"
    )
    assert "rate_limit" in _json_config, "config.json parsed but carries no rate_limit section"


def test_secrets_do_not_leak_into_the_suite() -> None:
    """`.env` must not reach `Settings` under test — the stance `config.py` documents.

    Two paths could load it (`_dotenv` at the top of config.py, and
    `Settings.Config.env_file`), and both are cwd-relative on purpose: under the
    documented workflow (`cd backend && pytest`, which is what `make test-backend` and
    CI both do) neither finds the project-root file, so test inputs don't vary with
    whatever a developer happens to hold. That was a comment and nothing more until
    this assertion.

    A failure here almost certainly means pytest was invoked from the project root
    rather than from `backend/`. That is not a flaky test — it is the limitation
    `config.py` calls out, made visible: your real `.env` is feeding `settings`, live
    API keys included. Run from `backend/`, or fix the cwd-dependence for real (pin the
    cwd, or gate on an explicit test environment). Do not weaken this assertion.
    """
    from config import settings

    assert not settings.anthropic_api_key, (
        "settings.anthropic_api_key is populated under test — the project-root .env "
        "reached Settings. Run pytest from backend/ (see the docstring)."
    )


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
