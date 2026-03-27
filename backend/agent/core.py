import json
from typing import AsyncGenerator, Optional
from providers.base import BaseLLMProvider
from providers.factory import get_llm_provider
from agent.rag import rag_engine
from agent.tools import tool_executor


SYSTEM_PROMPT_TEMPLATE = """Bạn là trợ lý AI cho website "{site_name}" ({site_url}).
Nhiệm vụ của bạn là giúp người dùng tìm thông tin và thực hiện các thao tác trên website.

Quy tắc:
- Trả lời bằng ngôn ngữ mà người dùng sử dụng
- Chỉ sử dụng thông tin từ knowledge base được cung cấp
- Nếu không biết, hãy nói rõ và gợi ý cách tìm thêm thông tin
- Trả lời ngắn gọn, dễ hiểu
- Khi cần thực hiện action, hãy giải thích trước và xin xác nhận

{context_section}

{knowledge_section}
"""


class ChatAgent:
    """Main chat agent that orchestrates RAG, tools, and LLM."""

    def __init__(
        self,
        site_id: str,
        site_name: str,
        site_url: str,
        llm_provider: str = "claude",
        llm_model: str = "claude-sonnet-4-20250514",
    ):
        self.site_id = site_id
        self.site_name = site_name
        self.site_url = site_url
        self.provider: BaseLLMProvider = get_llm_provider(llm_provider, llm_model)
        self.messages: list[dict] = []

    async def _build_system_prompt(
        self,
        query: str,
        page_context: Optional[dict] = None,
    ) -> str:
        context_section = ""
        if page_context:
            context_section = f"""Người dùng đang xem trang:
- URL: {page_context.get('url', 'N/A')}
- Tiêu đề: {page_context.get('title', 'N/A')}
- Nội dung: {page_context.get('pageText', '')[:1500]}"""

        knowledge_section = ""
        try:
            embedding_provider = get_llm_provider("openai")
            query_embedding = (await embedding_provider.embed([query]))[0]
            chunks = await rag_engine.search(self.site_id, query_embedding, top_k=5)

            if chunks:
                knowledge_parts = []
                for i, chunk in enumerate(chunks):
                    source = chunk["metadata"].get("source_url", "")
                    title = chunk["metadata"].get("title", "")
                    knowledge_parts.append(
                        f"[{i+1}] {title} ({source})\n{chunk['content']}"
                    )
                knowledge_section = (
                    "Thông tin từ knowledge base:\n\n"
                    + "\n\n---\n\n".join(knowledge_parts)
                )
        except Exception:
            knowledge_section = "(Knowledge base chưa được thiết lập)"

        return SYSTEM_PROMPT_TEMPLATE.format(
            site_name=self.site_name,
            site_url=self.site_url,
            context_section=context_section,
            knowledge_section=knowledge_section,
        )

    async def stream_response(
        self,
        message: str,
        page_context: Optional[dict] = None,
        repos=None,
    ) -> AsyncGenerator[str, None]:
        """Process a user message and stream the response."""
        self.messages.append({"role": "user", "content": message})

        system_prompt = await self._build_system_prompt(message, page_context)

        tools = []
        if repos:
            tools = await tool_executor.get_tools_for_site(repos, self.site_id)

        full_response = ""
        async for token in self.provider.stream(
            messages=self.messages,
            system_prompt=system_prompt,
            tools=tools if tools else None,
        ):
            full_response += token
            yield token

        self.messages.append({"role": "assistant", "content": full_response})

    async def get_response(
        self,
        message: str,
        page_context: Optional[dict] = None,
        repos=None,
    ) -> str:
        """Process a user message and return the full response."""
        self.messages.append({"role": "user", "content": message})
        system_prompt = await self._build_system_prompt(message, page_context)

        tools = []
        if repos:
            tools = await tool_executor.get_tools_for_site(repos, self.site_id)

        result = await self.provider.chat(
            messages=self.messages,
            system_prompt=system_prompt,
            tools=tools if tools else None,
        )

        if result.get("tool_calls"):
            for tc in result["tool_calls"]:
                tool_meta = next(
                    (t["_meta"] for t in tools if t["name"] == tc["name"]), None
                )
                if tool_meta:
                    tool_result = await tool_executor.execute_tool(
                        tool_meta, tc["arguments"]
                    )
                    self.messages.append({
                        "role": "assistant",
                        "content": f"Calling tool: {tc['name']}",
                    })
                    self.messages.append({
                        "role": "user",
                        "content": f"Tool result: {json.dumps(tool_result, ensure_ascii=False)}",
                    })
                    final = await self.provider.chat(
                        messages=self.messages,
                        system_prompt=system_prompt,
                    )
                    result = final

        self.messages.append({"role": "assistant", "content": result["content"]})
        return result["content"]
