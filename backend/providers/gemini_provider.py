from collections.abc import AsyncGenerator

import google.generativeai as genai

from providers.base import BaseLLMProvider


class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        genai.configure(api_key=api_key)
        self.model_name = model
        # Gemini doesn't expose reliable token counts through this SDK path.
        self.last_usage: dict | None = None

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> dict:
        model = genai.GenerativeModel(
            self.model_name,
            system_instruction=system_prompt if system_prompt else None,
        )
        # Convert messages to Gemini format
        history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [msg["content"]]})

        chat = model.start_chat(history=history)
        last_msg = messages[-1]["content"] if messages else ""
        response = await chat.send_message_async(
            last_msg,
            generation_config=genai.GenerationConfig(temperature=temperature),
        )
        return {"content": response.text, "tool_calls": [], "stop_reason": "end_turn"}

    async def stream(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        model = genai.GenerativeModel(
            self.model_name,
            system_instruction=system_prompt if system_prompt else None,
        )
        history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [msg["content"]]})

        chat = model.start_chat(history=history)
        last_msg = messages[-1]["content"] if messages else ""
        response = await chat.send_message_async(
            last_msg,
            generation_config=genai.GenerationConfig(temperature=temperature),
            stream=True,
        )
        async for chunk in response:
            if chunk.text:
                yield chunk.text

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio
        loop = asyncio.get_event_loop()
        results = []
        for text in texts:
            result = await loop.run_in_executor(
                None,
                lambda t=text: genai.embed_content(
                    model="models/text-embedding-004",
                    content=t,
                ),
            )
            results.append(result["embedding"])
        return results

    @staticmethod
    def available_models() -> list[dict]:
        return [
            {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "description": "Fast & efficient"},
            {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "description": "Most capable Gemini"},
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "description": "Next-gen speed"},
        ]
