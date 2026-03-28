import json
from typing import AsyncGenerator, Optional
from providers.base import BaseLLMProvider
from providers.factory import get_llm_provider
from agent.rag import rag_engine
from agent.tools import tool_executor
from knowledge.embed_cache import embed_cache
from config import settings


SYSTEM_PROMPT_TEMPLATE = """You are an AI assistant for the website "{site_name}" ({site_url}).

## Your Role
You operate in two modes:

### 1. Knowledge Mode (Guidance)
Based on content crawled from the website, you help users by:
- Answering questions about the website, products, and services
- Providing step-by-step instructions for using the website
- Delivering accurate information from the knowledge base
- If no relevant information is found, clearly state so and suggest alternatives

### 2. Action Mode (Execute on behalf)
When API tools are available, you perform actions for the user:
- Search products, place orders, register accounts
- Fill forms, look up information
- ALWAYS explain the action before executing it
- ALWAYS ask for confirmation before performing critical actions

## Rules
- Respond in the same language the user is using
- Prioritize answering from the knowledge base first
- If a suitable tool exists, suggest performing the action
- Keep responses concise and friendly

{memory_section}

{context_section}

{knowledge_section}

{tools_section}
"""


class ChatAgent:
    """Main chat agent — supports two modes: Knowledge (guidance) and Action (execute on behalf)."""

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
        repos=None,
        visitor_id: Optional[str] = None,
        conversation_summary: Optional[str] = None,
    ) -> tuple[str, list[dict]]:
        """Build system prompt and return (prompt, tools)."""

        # --- Visitor memory ---
        memory_section = ""
        if visitor_id and repos:
            try:
                memories = await repos.visitor_memories.list_by_visitor(visitor_id, self.site_id)
                if memories:
                    memory_parts = []
                    for mem in memories:
                        memory_parts.append(f"- {mem['key']}: {mem['value']}")
                    memory_section = (
                        "## What you know about this visitor (from previous conversations)\n"
                        + "\n".join(memory_parts)
                        + "\n\nUse this information naturally. Don't explicitly mention that you "
                        + "'remember' unless the visitor asks. Just apply the knowledge contextually."
                    )
            except Exception:
                pass  # visitor_memories repo may not exist yet

        if conversation_summary:
            memory_section += f"\n\n## Earlier in this conversation\n{conversation_summary}"

        # --- Page context ---
        context_section = ""
        if page_context:
            context_section = f"""## Current Page
- URL: {page_context.get('url', 'N/A')}
- Title: {page_context.get('title', 'N/A')}
- Page content: {page_context.get('pageText', '')[:1500]}"""

        # --- Knowledge (from crawl) ---
        knowledge_section = ""
        try:
            # Check embedding cache first
            query_embedding = embed_cache.get(query)
            if query_embedding is None:
                embedding_provider = get_llm_provider(
                    settings.embedding_provider,
                    settings.embedding_model,
                )
                query_embedding = (await embedding_provider.embed([query]))[0]
                embed_cache.put(query, query_embedding)

            chunks = await rag_engine.search(self.site_id, query_embedding, top_k=10)

            if chunks:
                knowledge_parts = []
                for i, chunk in enumerate(chunks):
                    source = chunk["metadata"].get("source_url", "")
                    title = chunk["metadata"].get("title", "")
                    score = chunk.get("score", 0)
                    knowledge_parts.append(
                        f"[{i+1}] {title} ({source}) [relevance: {score:.0%}]\n{chunk['content']}"
                    )
                knowledge_section = (
                    "## Knowledge Base (crawled content)\n"
                    "When answering from the knowledge base, cite sources using [1], [2] etc.\n\n"
                    + "\n\n---\n\n".join(knowledge_parts)
                )
            else:
                knowledge_section = "## Knowledge Base\n(No data available — direct the user to the main website page)"
        except Exception:
            knowledge_section = "## Knowledge Base\n(Not configured)"

        # --- Tools (API actions) ---
        tools = []
        tools_section = ""
        if repos:
            tools = await tool_executor.get_tools_for_site(repos, self.site_id)
            if tools:
                tool_names = [f"- {t['name']}: {t['description']}" for t in tools]
                tools_section = (
                    "## API Tools (you can perform actions on behalf of the user)\n"
                    + "\n".join(tool_names)
                    + "\n\nWhen the user needs to perform an action, use the appropriate tool. "
                    + "Always explain before calling a tool."
                )
            else:
                tools_section = "## API Tools\n(No tools configured — Knowledge/guidance mode only)"

        prompt = SYSTEM_PROMPT_TEMPLATE.format(
            site_name=self.site_name,
            site_url=self.site_url,
            memory_section=memory_section,
            context_section=context_section,
            knowledge_section=knowledge_section,
            tools_section=tools_section,
        )

        return prompt, tools

    async def stream_response(
        self,
        message: str,
        page_context: Optional[dict] = None,
        repos=None,
        visitor_id: Optional[str] = None,
        conversation_summary: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Process user message → stream response with tool calling support."""
        self.messages.append({"role": "user", "content": message})

        system_prompt, tools = await self._build_system_prompt(
            message, page_context, repos, visitor_id, conversation_summary,
        )

        # First, use non-streaming call to detect tool calls
        max_tool_rounds = 3
        round_count = 0

        if tools:
            result = await self.provider.chat(
                messages=self.messages,
                system_prompt=system_prompt,
                tools=tools,
            )

            while result.get("tool_calls") and round_count < max_tool_rounds:
                round_count += 1
                for tc in result["tool_calls"]:
                    tool_meta = next(
                        (t["_meta"] for t in tools if t["name"] == tc["name"]), None
                    )
                    if tool_meta:
                        # Notify the client about the tool call
                        yield f"\n\n> Calling **{tc['name']}**...\n\n"

                        tool_result = await tool_executor.execute_tool(
                            tool_meta, tc["arguments"]
                        )
                        self.messages.append({
                            "role": "assistant",
                            "content": f"Executing: {tc['name']}({json.dumps(tc['arguments'], ensure_ascii=False)})",
                        })
                        self.messages.append({
                            "role": "user",
                            "content": f"Tool result {tc['name']}: {json.dumps(tool_result, ensure_ascii=False)}",
                        })

                # Check for more tool calls
                result = await self.provider.chat(
                    messages=self.messages,
                    system_prompt=system_prompt,
                    tools=tools,
                )

            # If the last non-streaming call had no tool calls but produced content,
            # we still want to stream the final response for a better UX.
            # Only skip streaming if there were tool rounds and we already have content.

        # Stream the final response (no tools needed since tool calls are resolved)
        full_response = ""
        async for token in self.provider.stream(
            messages=self.messages,
            system_prompt=system_prompt,
            tools=None,
        ):
            full_response += token
            yield token

        self.messages.append({"role": "assistant", "content": full_response})

    async def get_response(
        self,
        message: str,
        page_context: Optional[dict] = None,
        repos=None,
        visitor_id: Optional[str] = None,
        conversation_summary: Optional[str] = None,
    ) -> str:
        """Process user message → full response with tool calling."""
        self.messages.append({"role": "user", "content": message})
        system_prompt, tools = await self._build_system_prompt(
            message, page_context, repos, visitor_id, conversation_summary,
        )

        result = await self.provider.chat(
            messages=self.messages,
            system_prompt=system_prompt,
            tools=tools if tools else None,
        )

        # Handle tool calls (Action mode)
        max_tool_rounds = 3  # Prevent infinite loops
        round_count = 0
        while result.get("tool_calls") and round_count < max_tool_rounds:
            round_count += 1
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
                        "content": f"Executing: {tc['name']}({json.dumps(tc['arguments'], ensure_ascii=False)})",
                    })
                    self.messages.append({
                        "role": "user",
                        "content": f"Tool result {tc['name']}: {json.dumps(tool_result, ensure_ascii=False)}",
                    })

            result = await self.provider.chat(
                messages=self.messages,
                system_prompt=system_prompt,
                tools=tools if tools else None,
            )

        self.messages.append({"role": "assistant", "content": result["content"]})
        return result["content"]
