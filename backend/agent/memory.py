"""Memory extraction and conversation summarization services.

Uses the site's LLM to extract structured facts from conversations
and summarize long conversations to reduce token usage.

A summary only reduces anything if the history it covers stops being sent as well, so
this module also owns the trimming primitives the transports use to bound what reaches
the LLM (``trim_messages_for_context`` / ``trim_start_index``).
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
                    valid.append(
                        {
                            "category": item["category"],
                            "key": item["key"],
                            "value": item["value"],
                            "confidence": item.get("confidence", "medium"),
                        }
                    )
            return valid

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Memory extraction parse failed", error=str(e))
            return []
        except Exception as e:
            logger.error("Memory extraction failed", error=str(e))
            return []


# Anthropic content-block types that only exist to carry a tool call or its result.
_TOOL_BLOCK_TYPES = frozenset({"tool_use", "tool_result"})


def _is_tool_exchange_message(msg: dict) -> bool:
    """True for messages that exist only to carry a tool call or its result.

    Covers the provider shapes ``ChatAgent._append_tool_messages`` writes: Anthropic
    ``tool_use``/``tool_result`` content blocks, and the OpenAI-compatible assistant
    ``tool_calls`` message plus its ``role: "tool"`` reply. The Gemini branch writes
    plain prose with no structural marker, so it counts as ordinary conversation —
    it carries no provider-level pairing that trimming could break, and
    ``GeminiProvider.supports_tools`` is False so that branch is unreachable anyway.
    """
    if msg.get("role") == "tool":
        return True
    # ``tool_calls`` is overloaded: ``_append_tool_messages`` writes OpenAI tool-call
    # objects (which carry an ``id``), while a *persisted* assistant message carries the
    # analytics record ``{"name", "success"}`` under the same key. Only the former is
    # part of a tool exchange; the latter is an ordinary assistant turn.
    if any(isinstance(call, dict) and "id" in call for call in msg.get("tool_calls") or []):
        return True
    content = msg.get("content")
    if isinstance(content, list):
        return any(isinstance(block, dict) and block.get("type") in _TOOL_BLOCK_TYPES for block in content)
    return False


def _is_turn_start(msg: dict) -> bool:
    """True when a trimmed conversation may begin at ``msg``.

    Only a plain visitor message qualifies. Beginning on an assistant message, on a
    ``tool_result`` whose ``tool_use`` was cut away, or on a ``role: "tool"`` reply
    each produce a conversation the provider APIs reject.
    """
    return msg.get("role") == "user" and not _is_tool_exchange_message(msg)


def trim_start_index(messages: list[dict], keep_recent: int) -> int:
    """Index of the oldest message to keep when retaining the last ``keep_recent`` turns.

    Returns 0 when nothing can be dropped. Tool-exchange messages do not count towards
    ``keep_recent``: the persisted history a summary is built from holds only visitor and
    assistant turns, so counting the same way keeps the two views of "how far back"
    aligned. The index is then walked back to the nearest turn start, which is what
    guarantees a tool result is never separated from the tool call it answers.
    """
    keep_recent = max(1, keep_recent)
    start = len(messages)
    kept = 0
    for i in range(len(messages) - 1, -1, -1):
        if not _is_tool_exchange_message(messages[i]):
            kept += 1
            if kept > keep_recent:
                break
        start = i
    while start > 0 and not _is_turn_start(messages[start]):
        start -= 1
    return start


def trim_messages_for_context(messages: list[dict], keep_recent: int) -> list[dict]:
    """Return the tail of ``messages`` still worth sending once a summary covers the rest.

    Never mutates the input: the persisted session record keeps the full history for the
    dashboard's Chat Log and the analytics endpoints. Only the LLM-facing copy shrinks.
    """
    return list(messages[trim_start_index(messages, keep_recent) :])


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
