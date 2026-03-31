from providers.base import BaseLLMProvider
from config import settings

# In-memory cache for DB keys (refreshed on each provider creation)
_key_cache: dict[str, str] = {}


async def _load_db_key(provider: str) -> str | None:
    """Load API key from DB, cache it."""
    try:
        from routers.llm_keys import get_key_for_provider
        key = await get_key_for_provider(provider)
        if key:
            _key_cache[provider] = key
        return key
    except Exception as e:
        from logging_config import logger
        logger.warning("Failed to load DB key for provider", provider=provider, error=str(e))
        return _key_cache.get(provider)


async def load_provider_key(provider: str) -> str | None:
    """Public helper to refresh a single provider key from DB into cache."""
    return await _load_db_key(provider)


def clear_provider_key(provider: str) -> None:
    """Remove a cached provider key after deletion."""
    _key_cache.pop(provider, None)


def _get_key(provider: str, env_key: str | None) -> str | None:
    """Get key: DB cache first, then .env fallback."""
    return _key_cache.get(provider) or env_key


def get_llm_provider(
    provider: str | None = None,
    model: str | None = None,
) -> BaseLLMProvider:
    """Factory function to create LLM provider instances."""
    provider = provider or settings.llm_provider
    model = model or settings.llm_model

    if provider == "claude":
        from providers.claude_provider import ClaudeProvider
        return ClaudeProvider(api_key=_get_key("claude", settings.anthropic_api_key), model=model)

    elif provider == "openai":
        from providers.openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=_get_key("openai", settings.openai_api_key), model=model)

    elif provider == "gemini":
        from providers.gemini_provider import GeminiProvider
        return GeminiProvider(api_key=_get_key("gemini", settings.gemini_api_key), model=model)

    elif provider == "ollama":
        from providers.ollama_provider import OllamaProvider
        return OllamaProvider(base_url=settings.ollama_base_url, model=model)

    elif provider == "lmstudio":
        from providers.openai_provider import OpenAIProvider
        p = OpenAIProvider(api_key="lm-studio", model=model)
        p.client = __import__("openai").AsyncOpenAI(
            api_key="lm-studio",
            base_url=settings.lmstudio_base_url,
        )
        return p

    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


async def refresh_key_cache():
    """Refresh all keys from DB into cache. Called after key save."""
    for p in ["claude", "openai", "gemini"]:
        await _load_db_key(p)


def get_all_providers() -> list[dict]:
    """Return info about all available providers and their models."""
    from providers.claude_provider import ClaudeProvider
    from providers.openai_provider import OpenAIProvider
    from providers.gemini_provider import GeminiProvider
    from providers.ollama_provider import OllamaProvider

    return [
        {
            "id": "claude",
            "name": "Claude (Anthropic)",
            "models": ClaudeProvider.available_models(),
            "requires_key": True,
            "has_key": bool(_get_key("claude", settings.anthropic_api_key)),
        },
        {
            "id": "openai",
            "name": "OpenAI",
            "models": OpenAIProvider.available_models(),
            "requires_key": True,
            "has_key": bool(_get_key("openai", settings.openai_api_key)),
        },
        {
            "id": "gemini",
            "name": "Gemini (Google)",
            "models": GeminiProvider.available_models(),
            "requires_key": True,
            "has_key": bool(_get_key("gemini", settings.gemini_api_key)),
        },
        {
            "id": "ollama",
            "name": "Ollama (Local)",
            "models": OllamaProvider.available_models(),
            "requires_key": False,
            "has_key": True,
        },
        {
            "id": "lmstudio",
            "name": "LM Studio (Local)",
            "models": [
                {"id": "google/gemma-3-4b", "name": "Gemma 3 4B", "description": "Local model via LM Studio"},
            ],
            "requires_key": False,
            "has_key": True,
        },
    ]


def get_embedding_providers() -> list[dict]:
    """Return info about providers that support embeddings."""
    return [
        {
            "id": "openai",
            "name": "OpenAI",
            "models": [
                {"id": "text-embedding-3-small", "name": "Embedding 3 Small"},
                {"id": "text-embedding-3-large", "name": "Embedding 3 Large"},
                {"id": "text-embedding-ada-002", "name": "Embedding Ada 002"},
            ],
            "requires_key": True,
            "has_key": bool(_get_key("openai", settings.openai_api_key)),
        },
        {
            "id": "ollama",
            "name": "Ollama (Local)",
            "models": [
                {"id": "nomic-embed-text", "name": "Nomic Embed Text"},
            ],
            "requires_key": False,
            "has_key": True,
        },
        {
            "id": "lmstudio",
            "name": "LM Studio (Local)",
            "models": [
                {"id": "text-embedding-nomic-embed-text-v1.5", "name": "Nomic Embed v1.5"},
            ],
            "requires_key": False,
            "has_key": True,
        },
    ]
