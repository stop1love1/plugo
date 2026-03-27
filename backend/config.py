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

    # Server
    backend_port: int = 8000
    widget_cdn_url: str = "http://localhost:8000/static/widget.js"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
