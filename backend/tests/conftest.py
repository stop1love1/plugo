"""Shared test fixtures for the Plugo backend."""

import contextlib
import os
import sys

import pytest
from httpx import ASGITransport, AsyncClient

# Add backend directory to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Override env before importing app
os.environ["DATABASE_PROVIDER"] = "sqlite"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test.db"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["CHROMA_PATH"] = "./data/test_chroma"
# Admin credentials: config.json ships with empty values and the backend refuses
# to start with empty or legacy-default ("pluginme") credentials. Patch the
# loaded settings with a dedicated test credential after import.
from config import settings as _settings

_settings.admin_username = "plugo"
_settings.admin_password = "test-admin-password"

# Ensure data dir exists
os.makedirs(os.path.join(os.path.dirname(__file__), "..", "data"), exist_ok=True)

_db_initialized = False


async def _ensure_db():
    global _db_initialized
    if not _db_initialized:
        # Import all models so Base.metadata knows about all tables
        from database import Base, engine

        import models  # noqa: F401

        # Drop and recreate all tables to ensure schema is up-to-date
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        _db_initialized = True


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Create an async test client for the FastAPI app."""
    await _ensure_db()
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_repos():
    """Get repository instances for direct DB manipulation in tests."""
    await _ensure_db()
    from repositories import create_repos

    return await create_repos()


@pytest.fixture
async def auth_headers():
    """Return Authorization headers with a valid JWT token."""
    from auth import create_access_token

    token = create_access_token(subject="plugo", role="admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def test_site(db_repos, auth_headers):
    """Create a test site and return its data."""
    site = await db_repos.sites.create({
        "name": "Test Site",
        "url": "https://example.com",
        "llm_provider": "claude",
        "llm_model": "claude-sonnet-4-20250514",
        "primary_color": "#6366f1",
        "greeting": "Hello!",
        "allowed_domains": "",
    })
    yield site
    # Cleanup
    with contextlib.suppress(Exception):
        await db_repos.sites.delete(site["id"])
