import json
from typing import AsyncGenerator, Optional
import httpx
from providers.base import BaseLLMProvider


class OllamaProvider(BaseLLMProvider):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
    ) -> dict:
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(messages)

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": msgs,
                    "stream": False,
                    "options": {"temperature": temperature},
                },
            )
            data = response.json()
            return {
                "content": data.get("message", {}).get("content", ""),
                "tool_calls": [],
                "stop_reason": "end_turn",
            }

    async def stream(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(messages)

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": msgs,
                    "stream": True,
                    "options": {"temperature": temperature},
                },
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio
        async with httpx.AsyncClient(timeout=60) as client:
            tasks = [
                client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": "nomic-embed-text", "prompt": text},
                )
                for text in texts
            ]
            responses = await asyncio.gather(*tasks)
        return [r.json().get("embedding", []) for r in responses]

    @staticmethod
    def available_models() -> list[dict]:
        return [
            {"id": "llama3", "name": "Llama 3", "description": "Meta's open model"},
            {"id": "mistral", "name": "Mistral 7B", "description": "Fast & efficient"},
            {"id": "codellama", "name": "Code Llama", "description": "Optimized for code"},
            {"id": "gemma2", "name": "Gemma 2", "description": "Google's open model"},
        ]
