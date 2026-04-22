from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator


class BaseLLMProvider(ABC):
    """Base interface for all LLM providers.

    Providers that can report token usage populate `last_usage` after each
    chat() or stream() call with {"input_tokens": int, "output_tokens": int}.
    Providers without reliable usage reporting leave it as None.
    """

    # Must be initialized by subclasses (or set here so attribute always exists).
    last_usage: dict | None = None

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> dict:
        """Send messages and get a complete response.

        If the provider reports usage, the returned dict includes a `usage` key:
        {"input_tokens": int, "output_tokens": int}.
        """
        pass

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """Send messages and stream the response token by token.

        After the stream completes, providers that report usage populate
        `self.last_usage`. Callers should read it once the generator ends.
        """
        pass

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        pass

    @staticmethod
    def available_models() -> list[dict]:
        """Return list of available models for this provider."""
        return []
