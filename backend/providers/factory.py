from providers.base import BaseLLMProvider
from config import settings


def get_llm_provider(
    provider: str | None = None,
    model: str | None = None,
) -> BaseLLMProvider:
    """Factory function to create LLM provider instances."""
    provider = provider or settings.llm_provider
    model = model or settings.llm_model

    if provider == "claude":
        from providers.claude_provider import ClaudeProvider
        return ClaudeProvider(api_key=settings.anthropic_api_key, model=model)

    elif provider == "openai":
        from providers.openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=settings.openai_api_key, model=model)

    elif provider == "gemini":
        from providers.gemini_provider import GeminiProvider
        return GeminiProvider(api_key=settings.gemini_api_key, model=model)

    elif provider == "ollama":
        from providers.ollama_provider import OllamaProvider
        return OllamaProvider(base_url=settings.ollama_base_url, model=model)

    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


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
        },
        {
            "id": "openai",
            "name": "OpenAI",
            "models": OpenAIProvider.available_models(),
            "requires_key": True,
        },
        {
            "id": "gemini",
            "name": "Gemini (Google)",
            "models": GeminiProvider.available_models(),
            "requires_key": True,
        },
        {
            "id": "ollama",
            "name": "Ollama (Local)",
            "models": OllamaProvider.available_models(),
            "requires_key": False,
        },
    ]
