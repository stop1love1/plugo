import json
from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from providers.base import BaseLLMProvider

_EMBEDDING_MODELS = {"text-embedding-ada-002", "text-embedding-3-small", "text-embedding-3-large"}


class OpenAIProvider(BaseLLMProvider):
    def is_embedding_model(self) -> bool:
        return self.model in _EMBEDDING_MODELS or "embed" in self.model

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> dict:
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(messages)

        kwargs = {
            "model": self.model,
            "messages": msgs,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = await self.client.chat.completions.create(**kwargs)
        return self._parse_response(response)

    async def stream(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(messages)

        kwargs = {
            "model": self.model,
            "messages": msgs,
            "temperature": temperature,
            "stream": True,
        }

        response = await self.client.chat.completions.create(**kwargs)
        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        embed_model = self.model if self.is_embedding_model() else "text-embedding-3-small"
        response = await self.client.embeddings.create(
            model=embed_model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool.get("parameters", {}),
                },
            }
            for tool in tools
        ]

    def _parse_response(self, response) -> dict:
        choice = response.choices[0]
        content = choice.message.content
        # When model returns only tool_calls (no text), keep content as None
        if not content and choice.message.tool_calls:
            content = None
        result = {"content": content, "tool_calls": []}
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                result["tool_calls"].append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                })
        result["stop_reason"] = choice.finish_reason
        return result

    @staticmethod
    def available_models() -> list[dict]:
        return [
            {"id": "gpt-4o", "name": "GPT-4o", "description": "Most capable OpenAI model"},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "description": "Fast & affordable"},
            {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "description": "High performance"},
        ]
