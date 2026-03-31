import json
from typing import AsyncGenerator, Optional
from providers.base import BaseLLMProvider
from providers.factory import get_llm_provider
from agent.rag import rag_engine
from agent.tools import tool_executor
from knowledge.embed_cache import embed_cache
from config import settings
from logging_config import logger


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

## Rich Content
You can include rich elements in your responses using extended markdown:
- **Images**: `![description](image_url)` — show product images, screenshots, banners
- **Image gallery**: Multiple images in a row become a slideshow:
  ```
  ![Product front](url1)
  ![Product side](url2)
  ```
- **Videos**: `![video](youtube_url)` — embed YouTube videos
- **Buttons**: `[Label](url "button")` — action buttons with site primary color
- **Button groups**: Consecutive buttons form a row:
  ```
  [Buy Now](/buy "button")
  [Learn More](/info "button")
  ```
- **Tables**: Use markdown tables for pricing, comparison, specs, schedules
- **Lists**: Use bullet/numbered lists for steps, features, FAQs
- **Bold/Italic**: Emphasize key info like prices, names, deadlines
- **Code blocks**: For technical content, API keys, config examples
- **Links**: `[text](url)` — inline links to pages

Use rich elements proactively when they improve the experience. For example:
- E-commerce: show product images, price tables, "Add to Cart" buttons
- SaaS: feature comparison tables, pricing, "Sign Up" buttons
- Support: step-by-step lists, links to docs, video tutorials
- Restaurant/Hotel: image galleries, booking buttons, menu tables
- Education: video embeds, resource links, schedule tables

## Rules
- Respond in the same language the user is using
- ONLY answer questions related to the website, its products, services, and content from the knowledge base
- If the user asks about topics NOT covered in the knowledge base or unrelated to the website, politely decline and redirect them to topics you can help with
- Do NOT answer general knowledge questions, write code, solve math problems, or act as a general-purpose assistant
- Prioritize answering from the knowledge base first
- If a suitable tool exists, suggest performing the action
- Keep responses concise and friendly
- Use rich content (images, buttons, links) when it improves the user experience

{memory_section}

{context_section}

{knowledge_section}

{tools_section}
"""


class ChatAgent:
    """Main chat agent — supports two modes: Knowledge (guidance) and Action (execute on behalf)."""

    # Providers that typically don't support tool/function calling (read from config)
    _NO_TOOL_PROVIDERS = set(settings.no_tool_providers)

    def __init__(
        self,
        site_id: str,
        site_name: str,
        site_url: str,
        llm_provider: str = "claude",
        llm_model: str = "claude-sonnet-4-20250514",
        system_prompt: str = "",
        bot_rules: str = "",
        response_language: str = "auto",
    ):
        self.site_id = site_id
        self.site_name = site_name
        self.site_url = site_url
        self.custom_system_prompt = system_prompt
        self.bot_rules = bot_rules
        self.response_language = response_language  # "auto" | "vi" | "en"
        self.llm_provider_name = llm_provider
        self.provider: BaseLLMProvider = get_llm_provider(llm_provider, llm_model)
        self.messages: list[dict] = []
        self.supports_tools = llm_provider not in self._NO_TOOL_PROVIDERS

    @staticmethod
    def _is_likely_vietnamese(text: str) -> bool:
        lowered = text.lower()
        vietnamese_markers = (
            "không",
            "có",
            "gì",
            "như",
            "giải pháp",
            "cung cấp",
            "cung cap",
            "bao nhiêu",
            "ở đâu",
            "là gì",
            "la gi",
            "o dau",
            "khong",
        )
        return any(marker in lowered for marker in vietnamese_markers) or any(ord(ch) > 127 for ch in text)

    def _no_knowledge_response(self) -> str:
        if self._is_likely_vietnamese(self.messages[-1]["content"] if self.messages else ""):
            return (
                "Mình chưa có thông tin này trong Knowledge hiện tại của website, "
                "nên không thể trả lời chính xác. Bạn hãy crawl thêm nội dung liên quan "
                "hoặc kiểm tra trực tiếp trên trang web."
            )

        return (
            "I couldn't find this information in the current website knowledge base, "
            "so I can't answer it accurately. Please crawl more relevant content or "
            "check the website directly."
        )

    async def _build_system_prompt(
        self,
        query: str,
        page_context: Optional[dict] = None,
        repos=None,
        visitor_id: Optional[str] = None,
        conversation_summary: Optional[str] = None,
    ) -> tuple[str, list[dict], bool]:
        """Build system prompt and return (prompt, tools, has_knowledge_match)."""

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
            except AttributeError:
                pass  # visitor_memories repo not available
            except Exception as e:
                logger.warning("Failed to load visitor memories", error=str(e))

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
        has_knowledge_match = False
        try:
            # Check embedding cache first
            query_embedding = embed_cache.get(query)
            if query_embedding is None:
                try:
                    embedding_provider = get_llm_provider(
                        settings.embedding_provider,
                        settings.embedding_model,
                    )
                    query_embedding = (await embedding_provider.embed([query]))[0]
                    embed_cache.put(query, query_embedding)
                except Exception as e:
                    logger.warning(
                        "Embedding failed, continuing without knowledge base",
                        provider=settings.embedding_provider,
                        model=settings.embedding_model,
                        error=str(e),
                    )
                    knowledge_section = "## Knowledge Base\n(Temporarily unavailable)"
                    query_embedding = None

            if query_embedding is not None:
                chunks = await rag_engine.search(self.site_id, query_embedding, top_k=10)
                if chunks and repos:
                    try:
                        valid_chunk_ids = {
                            chunk["id"] for chunk in await repos.knowledge.get_many([chunk["id"] for chunk in chunks])
                        }
                        chunks = [chunk for chunk in chunks if chunk["id"] in valid_chunk_ids]
                    except AttributeError:
                        pass
                    except Exception as e:
                        logger.warning("Failed to validate knowledge chunks against DB", error=str(e))

                if chunks:
                    has_knowledge_match = True
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
                        "IMPORTANT: When answering from the knowledge base, you MUST cite your sources.\n"
                        "At the end of your answer, add a '**Sources:**' section listing the URLs you used, e.g.:\n"
                        "**Sources:**\n"
                        "- [Page Title](https://example.com/page)\n\n"
                        + "\n\n---\n\n".join(knowledge_parts)
                    )
                elif not knowledge_section:
                    knowledge_section = (
                        "## Knowledge Base\n(No data available — direct the user to the main website page)"
                    )
        except AttributeError:
            knowledge_section = "## Knowledge Base\n(Not configured)"
        except Exception as e:
            logger.warning("Failed to retrieve knowledge base", error=str(e))
            knowledge_section = "## Knowledge Base\n(Temporarily unavailable)"

        # --- Tools (API actions) ---
        # Skip tool loading for providers that don't support function calling (e.g. ollama, lmstudio)
        tools = []
        tools_section = ""
        if repos and self.supports_tools:
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

        # Inject custom system prompt from site settings
        if self.custom_system_prompt:
            prompt += f"\n\n## Custom Instructions\n{self.custom_system_prompt}"

        # Inject bot rules from site settings
        if self.bot_rules:
            rules_list = [r.strip() for r in self.bot_rules.strip().splitlines() if r.strip()]
            if rules_list:
                prompt += "\n\n## Site-specific Rules\n" + "\n".join(f"- {r}" for r in rules_list)

        # Inject response language instruction
        if self.response_language == "vi":
            prompt += "\n\n## Language\nYou MUST respond in Vietnamese (Tiếng Việt) at all times, regardless of the language the user writes in."
        elif self.response_language == "en":
            prompt += "\n\n## Language\nYou MUST respond in English at all times, regardless of the language the user writes in."
        else:
            prompt += "\n\n## Language\nDetect the language of the user's message and respond in the same language. If unclear, respond in Vietnamese."

        return prompt, tools, has_knowledge_match

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

        system_prompt, tools, has_knowledge_match = await self._build_system_prompt(
            message, page_context, repos, visitor_id, conversation_summary,
        )

        if not has_knowledge_match:
            fallback = self._no_knowledge_response()
            self.messages.append({"role": "assistant", "content": fallback})
            for token in fallback:
                yield token
            return

        # First, use non-streaming call to detect tool calls
        max_tool_rounds = 3
        round_count = 0

        if tools and self.supports_tools:
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
        system_prompt, tools, has_knowledge_match = await self._build_system_prompt(
            message, page_context, repos, visitor_id, conversation_summary,
        )

        if not has_knowledge_match:
            fallback = self._no_knowledge_response()
            self.messages.append({"role": "assistant", "content": fallback})
            return fallback

        effective_tools = tools if (tools and self.supports_tools) else None
        result = await self.provider.chat(
            messages=self.messages,
            system_prompt=system_prompt,
            tools=effective_tools,
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
                tools=effective_tools,
            )

        self.messages.append({"role": "assistant", "content": result["content"]})
        return result["content"]
