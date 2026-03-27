import os
import warnings
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # LLM
    llm_provider: str = "claude"
    llm_model: str = "claude-sonnet-4-20250514"

    # API Keys
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # Embedding
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"

    # Database
    database_provider: str = "sqlite"  # sqlite | mongodb
    database_url: str = "sqlite+aiosqlite:///./data/plugo.db"

    # MongoDB (when database_provider = "mongodb")
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_database: str = "plugo"

    # Vector Store
    chroma_path: str = "./data/chroma"

    # Security
    secret_key: str = "change-me-to-a-random-string"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Rate limiting
    rate_limit_default: str = "60/minute"
    rate_limit_chat: str = "30/minute"
    rate_limit_crawl: str = "5/minute"

    # Server
    backend_port: int = 8000
    widget_cdn_url: str = "http://localhost:8000/static/widget.js"

    # Auth
    auth_enabled: bool = True  # Set False to disable auth (for initial setup)

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()


def validate_settings():
    """Validate critical settings on startup. Call from lifespan."""
    _INSECURE_KEYS = {"change-me-to-a-random-string", "secret", "password", ""}

    if settings.secret_key in _INSECURE_KEYS:
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
