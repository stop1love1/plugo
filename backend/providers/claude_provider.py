from collections.abc import AsyncGenerator

import anthropic

from providers.base import BaseLLMProvider


class ClaudeProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model
        self.last_usage: dict | None = None

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> dict:
        kwargs = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = await self.client.messages.create(**kwargs)
        result = self._parse_response(response)
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.last_usage = {
                "input_tokens": getattr(usage, "input_tokens", 0) or 0,
                "output_tokens": getattr(usage, "output_tokens", 0) or 0,
            }
            result["usage"] = self.last_usage
        return result

    async def stream(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        kwargs = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        # Reset before each stream so stale data doesn't leak across calls.
        self.last_usage = None
        async with self.client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
            try:
                final_msg = await stream.get_final_message()
                usage = getattr(final_msg, "usage", None)
                if usage is not None:
                    self.last_usage = {
                        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
                        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
                    }
            except Exception:
                # Usage is best-effort — never break the stream if the SDK can't provide it.
                self.last_usage = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Claude doesn't have embeddings — delegate to OpenAI or Ollama
        raise NotImplementedError("Use OpenAI or Ollama for embeddings")

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert generic tool format to Anthropic tool format."""
        anthropic_tools = []
        for tool in tools:
            anthropic_tools.append({
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool.get("parameters", {}),
            })
        return anthropic_tools

    def _parse_response(self, response) -> dict:
        result = {"content": "", "tool_calls": []}
        for block in response.content:
            if block.type == "text":
                result["content"] += block.text
            elif block.type == "tool_use":
                result["tool_calls"].append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input,
                })
        result["stop_reason"] = response.stop_reason
        return result

    @staticmethod
    def available_models() -> list[dict]:
        return [
            {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "description": "Fast & smart"},
            {"id": "claude-opus-4-20250514", "name": "Claude Opus 4", "description": "Most capable"},
            {"id": "claude-haiku-3-5-20241022", "name": "Claude Haiku 3.5", "description": "Fastest, cheapest"},
        ]
