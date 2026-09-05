"""
Plugo configuration loader.

Priority: config.json (project settings) + .env (secrets only)
- config.json  → all non-secret configuration (committed as config.example.json)
- .env         → API keys, SECRET_KEY (never committed)
- Environment variables override both (for Docker/CI)
"""

import json
import os
import warnings
from pathlib import Path

from dotenv import dotenv_values
from pydantic_settings import BaseSettings

# --- Load .env file directly (bypass OS env for specific keys) ---
_dotenv = dotenv_values(Path(__file__).parent.parent / ".env")
if not _dotenv:
    _dotenv = dotenv_values(".env")

# --- Load config.json ---
# `.resolve()` is load-bearing, not decoration. `__file__` carries whatever path
# the importer put on sys.path, and `pathlib` walks `..` lexically rather than
# collapsing it: `tests/../config.py` (which is exactly what tests/conftest.py
# inserts) makes `.parent.parent` land in `tests/` instead of the project root,
# so every candidate below misses and *every* setting silently falls back to its
# hard-coded default. That made config.json a no-op for the whole test suite.
_HERE = Path(__file__).resolve()
_CONFIG_PATHS = [
    _HERE.parent.parent / "config.json",  # project root
    _HERE.parent / "config.json",  # backend/
    Path("config.json"),  # cwd
]

_json_config: dict = {}
for _path in _CONFIG_PATHS:
    if _path.exists():
        with open(_path, encoding="utf-8") as f:
            _json_config = json.load(f)
        break


def _get(section: str, key: str, default=None):
    """Get a value from the nested config.json structure."""
    return _json_config.get(section, {}).get(key, default)


class Settings(BaseSettings):
    # --- LLM (from config.json → llm) ---
    llm_provider: str = _get("llm", "provider", "claude")
    llm_model: str = _get("llm", "model", "claude-sonnet-4-20250514")

    # --- API Keys (from .env only — secrets) ---
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None

    # --- Ollama (from config.json → ollama) ---
    ollama_base_url: str = _get("ollama", "base_url", "http://localhost:11434")
    ollama_model: str = _get("ollama", "model", "llama3")

    # --- LM Studio (OpenAI-compatible local server) ---
    lmstudio_base_url: str = "http://localhost:1234/v1"

    # --- Embedding (from config.json → embedding) ---
    embedding_provider: str = _get("embedding", "provider", "openai")
    embedding_model: str = _get("embedding", "model", "text-embedding-3-small")
    embedding_cache_size: int = _get("embedding", "cache_size", 1000)
    embedding_cache_ttl: int = _get("embedding", "cache_ttl", 3600)

    # --- Database (from config.json → database) ---
    database_provider: str = _get("database", "provider", "sqlite")
    database_url: str = _get("database", "url", "sqlite+aiosqlite:///./data/plugo.db")
    mongodb_url: str = _get("database", "mongodb_url", "mongodb://localhost:27017")
    mongodb_database: str = _get("database", "mongodb_database", "plugo")

    # --- Vector Store (from config.json → vector_store) ---
    chroma_path: str = _get("vector_store", "chroma_path", "./data/chroma")

    # --- RAG Pipeline (from config.json → rag) ---
    rag_min_score: float = _get("rag", "min_score", 0.3)
    rag_max_chunks: int = _get("rag", "max_chunks", 7)

    # --- Security (SECRET_KEY from .env only, cors from config.json) ---
    secret_key: str = "change-me-to-a-random-string"
    cors_origins: str = ",".join(_get("server", "cors_origins", ["http://localhost:3000", "http://localhost:5173"]))

    # --- Rate Limiting (from config.json → rate_limit) ---
    rate_limit_default: str = _get("rate_limit", "default", "60/minute")
    rate_limit_chat: str = _get("rate_limit", "chat", "30/minute")
    rate_limit_crawl: str = _get("rate_limit", "crawl", "5/minute")
    # Strict per-IP limit on the admin login endpoint to blunt brute-force attempts.
    rate_limit_auth: str = _get("rate_limit", "auth", "5/minute")
    # Abuse ceiling per client IP, applied to each public (site-token) endpoint
    # separately — slowapi buckets per endpoint, so this is not a shared pool
    # across them. Those endpoints are *also* limited per site_token for tenant
    # fairness, but a site_token is caller-supplied, so rotating it mints a fresh
    # bucket; the IP-keyed limit is what a single source cannot rotate away.
    # Deliberately well above every per-tenant allowance so a well-behaved tenant
    # always meets its own fairness limit first — deployments whose visitors share
    # an egress IP raise this one without loosening tenant fairness.
    rate_limit_public_ip: str = _get("rate_limit", "public_ip", "120/minute")
    # The same ceiling for WebSocket *messages*, which needs its own value even
    # though a WS message and an SSE chat request cost exactly the same (one LLM
    # turn). What differs is the population sharing one address, and a ceiling is
    # sized by legitimate aggregate rate, not by cost per event: the widget speaks
    # WebSocket exclusively (`frontend/src/widget/ui/App.tsx`), so every visitor
    # lands here while the SSE route carries only direct API consumers.
    #
    # Sizing, from the message rate rather than the HTTP one. The widget disables
    # its own input while a reply streams (`ui/Window.tsx`), so a legitimate
    # visitor cannot send again until the LLM finishes — a hard floor of roughly
    # 8-10s per turn once reading and typing are counted, i.e. ~6 messages/minute
    # flat out and 2-4 typically. At 300/minute one address comfortably carries
    # ~50 simultaneously engaged chatters, which is what a corporate NAT or a
    # CGNAT block needs. Dividing by the per-session window instead gives the
    # abuse view: 300/20 means one address may run 15 sessions all at their own
    # maximum, a bounded multiplier on the reconnect it exists to catch.
    #
    # Note this cannot rescue the topology where `FORWARDED_ALLOW_IPS` is unset
    # and a reverse proxy fronts the backend — every visitor then presents as the
    # proxy and shares one bucket, and no finite value fixes that. Configuring
    # that variable does (see .env.example); this value keeps a small-to-medium
    # deployment working in the meantime.
    rate_limit_ws_public_ip: str = _get("rate_limit", "ws_public_ip", "300/minute")
    # Max simultaneous open SSE streams per site_token. Caps the long-lived
    # connection footprint that slowapi's per-window limiter can't see.
    rate_limit_sse_concurrent: int = _get("rate_limit", "sse_concurrent", 10)

    # --- Server (from config.json → server) ---
    backend_port: int = _get("server", "backend_port", 8000)
    widget_cdn_url: str = _get("server", "widget_cdn_url", "http://localhost:8000/static/widget.js")

    # --- Crawl (from config.json → crawl) ---
    crawl_verify_ssl: bool = _get("crawl", "verify_ssl", True)
    crawl_request_delay: float = _get("crawl", "request_delay", 1.0)
    crawl_request_timeout: int = _get("crawl", "request_timeout", 30)
    crawl_max_concurrent_fetches: int = _get("crawl", "max_concurrent_fetches", 5)
    crawl_max_concurrent_auto: int = _get("crawl", "max_concurrent_auto_crawls", 3)
    crawl_stale_timeout_minutes: int = _get("crawl", "stale_timeout_minutes", 30)
    crawl_max_continuous_rounds: int = _get("crawl", "max_continuous_rounds", 10)
    crawl_max_retries: int = _get("crawl", "max_retries", 2)
    crawl_scheduler_interval: int = _get("crawl", "scheduler_interval_seconds", 300)
    crawl_embed_batch_size: int = _get("crawl", "embed_batch_size", 200)

    # --- Session retention (from config.json → session) ---
    # Chat sessions older than this many days are purged by the scheduler. 0 disables.
    session_retention_days: int = _get("session", "retention_days", 90)

    # --- Auth (from config.json → auth) ---
    auth_enabled: bool = _get("auth", "enabled", True)

    # --- Admin Login (.env USERNAME/PASSWORD → config.json → default) ---
    # Read from .env directly to avoid Windows OS env conflict (USERNAME=Admin)
    admin_username: str = _dotenv.get("USERNAME", _get("auth", "username", "plugo"))
    admin_password: str = _dotenv.get("PASSWORD", _get("auth", "password", "pluginme"))

    # --- Agent (from config.json → agent) ---
    no_tool_providers: list[str] = _get("agent", "no_tool_providers", ["ollama", "lmstudio"])
    agent_system_prompt: str = _get("agent", "system_prompt", "")
    agent_no_knowledge_vi: str = _get("agent", "no_knowledge_response_vi", "")
    agent_no_knowledge_en: str = _get("agent", "no_knowledge_response_en", "")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()


def validate_settings():
    """Validate critical settings on startup. Call from lifespan."""
    insecure_keys = {"change-me-to-a-random-string", "secret", "password", ""}

    if settings.secret_key in insecure_keys:
        env = os.environ.get("ENV", "development")
        if env == "production":
            raise RuntimeError(
                "FATAL: SECRET_KEY is not set or insecure. "
                "Set a strong SECRET_KEY in .env before running in production."
            )
        else:
            warnings.warn(
                "WARNING: SECRET_KEY is using the default insecure value. "
                "Set a strong SECRET_KEY in .env before deploying.",
                stacklevel=2,
            )

    if len(settings.secret_key) < 16 and settings.secret_key not in insecure_keys:
        warnings.warn(
            "SECRET_KEY is shorter than 16 characters. Use a longer key for better security.",
            stacklevel=2,
        )

    if settings.auth_enabled and (
        not settings.admin_username or not settings.admin_password or settings.admin_password == "pluginme"
    ):
        raise RuntimeError(
            "FATAL: admin credentials are missing or use the legacy default. "
            "Set USERNAME and PASSWORD in .env — the default admin credentials "
            "must be changed before starting."
        )

    # In production, refuse to start with the docker-compose default MongoDB
    # password baked into the connection string.
    if (
        os.environ.get("ENV", "development") == "production"
        and settings.database_provider == "mongodb"
        and "plugo_dev_password" in settings.mongodb_url
    ):
        raise RuntimeError(
            "FATAL: MongoDB is using the default development password. "
            "Set a strong MONGO_PASSWORD before running in production."
        )
