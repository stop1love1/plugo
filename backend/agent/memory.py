"""Memory extraction and conversation summarization services.

Uses the site's LLM to extract structured facts from conversations
and summarize long conversations to reduce token usage.
"""

import json

from logging_config import logger

from providers.base import BaseLLMProvider


class MemoryExtractor:
    """Extracts visitor memories from conversations using LLM."""

    EXTRACTION_PROMPT = """Analyze this conversation and extract key facts about the visitor.
Return a JSON array of memory objects. Each object must have:
- "category": one of "identity", "preference", "issue", "context"
- "key": a short snake_case identifier (e.g., "name", "preferred_language", "past_issue_shipping")
- "value": the extracted information as a clear, concise statement
- "confidence": "high" if explicitly stated, "medium" if strongly implied, "low" if inferred

Only extract facts that are clearly useful for future interactions.
Do NOT extract transient information (e.g., "user asked about pricing" during a pricing conversation).
DO extract persistent facts (e.g., "user's name is Alice", "prefers Vietnamese", "had issue with order #123").

If no meaningful facts can be extracted, return an empty array: []

Conversation:
{conversation}

Return ONLY a valid JSON array, no other text."""

    @staticmethod
    def _format_conversation(messages: list[dict]) -> str:
        parts = []
        for msg in messages:
            role = "User" if msg.get("role") == "user" else "Assistant"
            content = msg.get("content", "")
            if content:
                parts.append(f"{role}: {content}")
        return "\n".join(parts)

    async def extract_memories(
        self,
        messages: list[dict],
        provider: BaseLLMProvider,
    ) -> list[dict]:
        """Extract memories from a list of messages."""
        conversation = self._format_conversation(messages)
        if len(conversation) < 50:
            return []

        try:
            prompt = self.EXTRACTION_PROMPT.format(conversation=conversation)
            result = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="You are a precise information extraction system. Return only valid JSON.",
            )

            content = result.get("content", "").strip()
            # Extract JSON from response (handle possible markdown wrapping)
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            extracted = json.loads(content)
            if not isinstance(extracted, list):
                return []

            # Validate structure
            valid = []
            for item in extracted:
                if (
                    isinstance(item, dict)
                    and "category" in item
                    and "key" in item
                    and "value" in item
                    and item["category"] in ("identity", "preference", "issue", "context")
                ):
                    valid.append({
                        "category": item["category"],
                        "key": item["key"],
                        "value": item["value"],
                        "confidence": item.get("confidence", "medium"),
                    })
            return valid

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Memory extraction parse failed", error=str(e))
            return []
        except Exception as e:
            logger.error("Memory extraction failed", error=str(e))
            return []


class ConversationSummarizer:
    """Summarizes long conversations to reduce token usage."""

    SUMMARY_PROMPT = """Summarize the following conversation between a visitor and an AI assistant.
Focus on:
1. What the visitor wanted/asked about
2. Key decisions or outcomes
3. Any unresolved issues
4. Important context for future reference

Keep the summary concise but preserve all actionable information.

{existing_context}

Conversation:
{conversation}

Summary:"""

    MESSAGE_THRESHOLD = 20
    KEEP_RECENT_MESSAGES = 6

    async def should_summarize(self, messages: list[dict]) -> bool:
        return len(messages) > self.MESSAGE_THRESHOLD

    async def summarize(
        self,
        messages: list[dict],
        provider: BaseLLMProvider,
        existing_summary: str | None = None,
    ) -> tuple[str, int]:
        """Summarize older messages. Returns (summary_text, messages_summarized_count)."""
        messages_to_summarize = messages[: -self.KEEP_RECENT_MESSAGES]
        if not messages_to_summarize:
            return existing_summary or "", 0

        existing_context = ""
        if existing_summary:
            existing_context = f"[Previous summary: {existing_summary}]\n"

        conversation = MemoryExtractor._format_conversation(messages_to_summarize)

        try:
            prompt = self.SUMMARY_PROMPT.format(
                existing_context=existing_context,
                conversation=conversation,
            )
            result = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="You are a concise conversation summarizer.",
            )
            summary_text = result.get("content", "").strip()
            return summary_text, len(messages_to_summarize)

        except Exception as e:
            logger.error("Summarization failed", error=str(e))
            return existing_summary or "", 0
