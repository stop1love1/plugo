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
_CONFIG_PATHS = [
    Path(__file__).parent.parent / "config.json",   # project root
    Path(__file__).parent / "config.json",           # backend/
    Path("config.json"),                             # cwd
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

    if settings.admin_password == "pluginme":
        warnings.warn(
            "WARNING: Admin password is still the default 'pluginme'. "
            "Set a strong PASSWORD in .env before deploying.",
            stacklevel=2,
        )
