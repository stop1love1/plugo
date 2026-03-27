"""Shared test fixtures for the Plugo backend."""

import os
import sys
import pytest
from httpx import ASGITransport, AsyncClient

# Add backend directory to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Override env before importing app
os.environ.setdefault("DATABASE_PROVIDER", "sqlite")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./data/test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("CHROMA_PATH", "./data/test_chroma")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Create an async test client for the FastAPI app."""
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
