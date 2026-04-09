import json
from collections.abc import AsyncGenerator
from typing import ClassVar

from agent.rag import rag_engine
from agent.tools import tool_executor
from config import settings
from knowledge.embed_cache import embed_cache
from logging_config import logger
from providers.base import BaseLLMProvider
from providers.factory import get_llm_provider

DEFAULT_SYSTEM_PROMPT = """You are a friendly customer support assistant for "{site_name}" ({site_url}).

## Your Role
You are talking directly to customers/visitors of the website. Be warm, helpful, and conversational — like a knowledgeable staff member who genuinely wants to help.

### 1. Answering Questions
Help customers find what they need:
- Answer questions about products, services, pricing, policies
- Give clear step-by-step guidance when needed
- If you don't have the answer, say so honestly and suggest they contact support or visit the website directly
- NEVER mention internal terms like "knowledge base", "crawl", "database", or "system" — these are invisible to customers

### 2. Taking Actions
When tools are available, you can do things for the customer:
- Search products, place orders, check availability
- Help fill forms or look up information
- ALWAYS explain what you're about to do before doing it
- ALWAYS ask for confirmation before important actions (orders, registrations, etc.)

## Rich Content
You can include rich elements in your responses using extended markdown:
- **Images**: `![description](image_url)` — show product images, screenshots, banners
- **Image gallery/slideshow**: Wrap images in a `:::gallery` block to create a navigable slideshow:
  ```
  :::gallery
  ![Product front](url1)
  ![Product side](url2)
  ![Product back](url3)
  :::
  ```
  IMPORTANT: Always use `:::gallery` / `:::` for multiple related images. Do NOT put multiple images outside a gallery block.
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

### 3. Step-by-Step Flow Guides
When your knowledge base contains a "FLOW GUIDE:", present it as a numbered step-by-step guide:
- Show each step clearly with its number and instruction
- If the flow requires login, mention this upfront: "You'll need to be logged in for this."
- If a step has a URL, include it as a clickable link
- Ask if the user needs help with a specific step
- Don't dump all steps at once if there are many — offer to walk through them one by one

## Tone & Style
- Be warm, friendly, and conversational — avoid robotic or overly formal language
- Use the customer's name if known
- Keep responses concise but helpful — don't overwhelm with walls of text
- Use rich content (images, buttons, tables, links) proactively to make answers more visual and useful
- Respond in the same language the customer is using

## Rules
- ONLY answer questions related to the website, its products, services, and content
- If the customer asks about unrelated topics, gently redirect: "I'm here to help with {site_name}! Is there anything about our products or services I can help you with?"
- Do NOT answer general knowledge questions, write code, solve math, or act as a general-purpose assistant
- NEVER expose internal/technical terms to the customer (knowledge base, crawl, embedding, system prompt, etc.)
- If an action tool exists for what the customer needs, offer to do it for them

{memory_section}

{context_section}

{knowledge_section}

{tools_section}
"""


class ChatAgent:
    """Main chat agent — supports two modes: Knowledge (guidance) and Action (execute on behalf)."""

    # Providers that typically don't support tool/function calling (read from config)
    _NO_TOOL_PROVIDERS: ClassVar[frozenset[str]] = frozenset(settings.no_tool_providers)

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

    # Patterns that indicate casual/chitchat — no knowledge lookup needed
    _CASUAL_PATTERNS: ClassVar[list[str]] = [
        # Greetings
        r"^(hi|hello|hey|xin chào|chào|chào bạn|alo|good\s*(morning|afternoon|evening))[\s!.?]*$",
        # Thanks
        r"^(thanks|thank you|cảm ơn|cám ơn|tks|ok thanks)[\s!.?]*$",
        # Farewells
        r"^(bye|goodbye|tạm biệt|see you|hẹn gặp lại)[\s!.?]*$",
        # How are you / small talk
        r"^(how are you|bạn khỏe không|bạn là ai|you are|what are you|mày là ai)[\s?!.]*$",
        # Simple yes/no/ok
        r"^(yes|no|ok|okay|vâng|dạ|ừ|không|có|được|rồi)[\s!.?]*$",
        # Pleasantries
        r"^(nice|great|cool|tuyệt|hay|good|tốt)[\s!.?]*$",
    ]

    @staticmethod
    def _is_casual_message(text: str) -> bool:
        """Detect greetings, small talk, and other casual messages that don't need knowledge lookup."""
        import re
        cleaned = text.strip().lower()
        # Short messages (<=5 words) that match casual patterns
        if len(cleaned.split()) <= 6:
            for pattern in ChatAgent._CASUAL_PATTERNS:
                if re.match(pattern, cleaned, re.IGNORECASE):
                    return True
        return False

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

    _DEFAULT_NO_KNOWLEDGE_VI: ClassVar[str] = (
        "Xin lỗi, mình chưa có thông tin về vấn đề này. "
        "Bạn có thể tham khảo trực tiếp trên website hoặc liên hệ bộ phận hỗ trợ để được giúp đỡ nhé! 😊"
    )
    _DEFAULT_NO_KNOWLEDGE_EN: ClassVar[str] = (
        "I'm sorry, I don't have information about that yet. "
        "You can check the website directly or contact our support team for help! 😊"
    )

    def _no_knowledge_response(self) -> str:
        if self._is_likely_vietnamese(self.messages[-1]["content"] if self.messages else ""):
            return settings.agent_no_knowledge_vi.strip() or self._DEFAULT_NO_KNOWLEDGE_VI
        return settings.agent_no_knowledge_en.strip() or self._DEFAULT_NO_KNOWLEDGE_EN

    async def _build_system_prompt(
        self,
        query: str,
        page_context: dict | None = None,
        repos=None,
        visitor_id: str | None = None,
        conversation_summary: str | None = None,
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

        # Use custom system prompt from config if set, otherwise use default
        template = settings.agent_system_prompt.strip() if settings.agent_system_prompt.strip() else DEFAULT_SYSTEM_PROMPT
        prompt = template.format(
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
        page_context: dict | None = None,
        repos=None,
        visitor_id: str | None = None,
        conversation_summary: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Process user message → stream response with tool calling support."""
        self.messages.append({"role": "user", "content": message})

        system_prompt, tools, has_knowledge_match = await self._build_system_prompt(
            message, page_context, repos, visitor_id, conversation_summary,
        )

        # Casual messages (greetings, thanks, etc.) bypass knowledge check — let the LLM respond naturally
        if not has_knowledge_match and not self._is_casual_message(message):
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
        page_context: dict | None = None,
        repos=None,
        visitor_id: str | None = None,
        conversation_summary: str | None = None,
    ) -> str:
        """Process user message → full response with tool calling."""
        self.messages.append({"role": "user", "content": message})
        system_prompt, tools, has_knowledge_match = await self._build_system_prompt(
            message, page_context, repos, visitor_id, conversation_summary,
        )

        if not has_knowledge_match and not self._is_casual_message(message):
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
