import json
import re
import uuid
import asyncio
from datetime import datetime, timezone
from time import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from repositories import create_repos
from agent.core import ChatAgent
from agent.memory import MemoryExtractor, ConversationSummarizer
from providers.factory import get_llm_provider
from logging_config import logger

router = APIRouter()

# Store active agents per session
active_agents: dict[str, ChatAgent] = {}

# --- WebSocket rate limiting ---
WS_RATE_LIMIT_WINDOW = 60  # seconds
WS_RATE_LIMIT_MAX = 20  # max messages per window per session


class WSRateLimiter:
    """Simple per-session rate limiter for WebSocket messages."""

    def __init__(self):
        self._timestamps: dict[str, list[float]] = {}

    def is_allowed(self, session_id: str) -> bool:
        now = time()
        timestamps = self._timestamps.get(session_id, [])
        # Remove expired timestamps
        timestamps = [t for t in timestamps if now - t < WS_RATE_LIMIT_WINDOW]
        if len(timestamps) >= WS_RATE_LIMIT_MAX:
            self._timestamps[session_id] = timestamps
            return False
        timestamps.append(now)
        self._timestamps[session_id] = timestamps
        return True

    def cleanup(self, session_id: str):
        self._timestamps.pop(session_id, None)


_ws_rate_limiter = WSRateLimiter()

# --- Site config cache ---
_site_cache: dict[str, tuple[dict, float]] = {}
CACHE_TTL = 60  # seconds
CACHE_MAX_SIZE = 100


async def get_cached_site(repos, site_token: str) -> dict | None:
    """Return site config from cache or DB, with a 60-second TTL."""
    now = time()
    if site_token in _site_cache:
        site, cached_at = _site_cache[site_token]
        if now - cached_at < CACHE_TTL:
            return site
        del _site_cache[site_token]
    site = await repos.sites.get_by_token(site_token)
    if site:
        if len(_site_cache) >= CACHE_MAX_SIZE:
            # Evict oldest entry
            oldest_key = min(_site_cache, key=lambda k: _site_cache[k][1])
            del _site_cache[oldest_key]
        _site_cache[site_token] = (site, now)
    return site


def invalidate_site_cache(site_token: str | None = None):
    """Invalidate site cache entries. If no token given, clear all."""
    if site_token:
        _site_cache.pop(site_token, None)
    else:
        _site_cache.clear()


@router.websocket("/ws/chat/{site_token}")
async def websocket_chat(websocket: WebSocket, site_token: str):
    """WebSocket endpoint for real-time chat streaming.

    Supports session resumption: if the client sends a `session_id` in
    the first message, the server restores the previous conversation
    from the database instead of creating a new session.
    """
    await websocket.accept()

    repos = await create_repos()

    # Find site by token (cached)
    site = await get_cached_site(repos, site_token)
    if not site:
        await websocket.send_json({"type": "error", "message": "Invalid site token"})
        await websocket.close()
        return

    # Validate WebSocket origin against site's allowed_domains
    origin = websocket.headers.get("origin", "")
    if site.get("allowed_domains"):
        allowed = [d.strip() for d in site["allowed_domains"].split(",") if d.strip()]
        if allowed:
            if not origin:
                await websocket.close(code=4003, reason="Origin required")
                return
            from urllib.parse import urlparse as _urlparse
            origin_host = _urlparse(origin).hostname
            if not origin_host or not any(origin_host == d or origin_host.endswith("." + d) for d in allowed):
                await websocket.close(code=4003, reason="Origin not allowed")
                return

    if not site.get("is_approved"):
        await websocket.send_json({"type": "error", "message": "Site is pending approval. Contact admin."})
        await websocket.close()
        return

    # Wait for the first message to check for session resumption
    # The client sends {"type": "init", "session_id": "...", "visitor_id": "..."} or just starts chatting
    first_data = await websocket.receive_json()

    session_id = None
    messages = []
    resumed = False

    # Sanitize visitor_id to prevent cross-site spoofing
    raw_visitor_id = first_data.get("visitor_id", "")
    # Only allow alphanumeric, hyphens, underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', str(raw_visitor_id))[:64] if raw_visitor_id else ""
    if not sanitized:
        sanitized = str(uuid.uuid4())
    # Scope to this site to prevent cross-site memory access
    visitor_id = f"{site['id']}:{sanitized}"

    # Check if client wants to resume an existing session
    if first_data.get("type") == "init" and first_data.get("session_id"):
        existing_session = await repos.chat_sessions.get_by_id(first_data["session_id"])
        if existing_session and existing_session.get("site_id") == site["id"]:
            # Allow resume if session is still open OR ended less than 5 minutes ago
            ended_at = existing_session.get("ended_at")
            can_resume = not ended_at
            if ended_at and isinstance(ended_at, str):
                try:
                    ended_time = datetime.fromisoformat(ended_at)
                    if ended_time.tzinfo is None:
                        ended_time = ended_time.replace(tzinfo=timezone.utc)
                    can_resume = (datetime.now(timezone.utc) - ended_time).total_seconds() < 300
                except ValueError:
                    pass
            elif ended_at and isinstance(ended_at, datetime):
                if ended_at.tzinfo is None:
                    ended_at = ended_at.replace(tzinfo=timezone.utc)
                can_resume = (datetime.now(timezone.utc) - ended_at).total_seconds() < 300

            if can_resume:
                session_id = existing_session["id"]
                messages = existing_session.get("messages", [])
                resumed = True
                # Clear ended_at since session is being resumed
                await repos.chat_sessions.set_ended(session_id, clear=True)
                # Use visitor_id from existing session if not provided
                if not visitor_id:
                    visitor_id = existing_session.get("visitor_id")
                logger.info("Session resumed", session_id=session_id, message_count=len(messages))

    # Create new session if not resuming
    if not session_id:
        session_data = {"site_id": site["id"]}
        if visitor_id:
            session_data["visitor_id"] = visitor_id
        chat_session = await repos.chat_sessions.create(session_data)
        session_id = chat_session["id"]

    # Create or restore agent
    agent = ChatAgent(
        site_id=site["id"],
        site_name=site["name"],
        site_url=site["url"],
        llm_provider=site["llm_provider"],
        llm_model=site["llm_model"],
    )

    # Restore agent conversation history from saved messages
    if resumed and messages:
        for msg in messages:
            role = "user" if msg["role"] == "user" else "assistant"
            agent.messages.append({"role": role, "content": msg["content"]})

    active_agents[session_id] = agent

    # Fetch conversation summary for resumed sessions
    conversation_summary = None
    if resumed:
        try:
            existing_summary = await repos.conversation_summaries.get_by_session(session_id)
            if existing_summary:
                conversation_summary = existing_summary["summary_text"]
        except Exception:
            pass  # conversation_summaries repo may not exist yet

    # Send welcome with session info and previous messages
    await websocket.send_json({
        "type": "connected",
        "session_id": session_id,
        "greeting": site["greeting"],
        "resumed": resumed,
        "history": [{"role": m["role"], "content": m["content"]} for m in messages] if resumed else [],
        "config": {
            "primaryColor": site["primary_color"],
            "position": site["position"],
        },
        "suggestions": site.get("suggestions") or [],
    })

    # If the first message was a chat message (not init), process it
    if first_data.get("type") != "init" and first_data.get("message"):
        await _handle_message(
            websocket, agent, repos, session_id, messages,
            first_data["message"], first_data.get("pageContext"),
            visitor_id, conversation_summary,
        )

    # Background heartbeat to detect stale connections
    heartbeat_active = True

    async def _heartbeat():
        """Send ping every 30 seconds to detect stale WebSocket connections."""
        try:
            while heartbeat_active:
                await asyncio.sleep(30)
                if not heartbeat_active:
                    break
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
        except asyncio.CancelledError:
            pass

    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        while True:
            data = await websocket.receive_json()

            # Handle pong from client
            if data.get("type") == "pong":
                continue

            message = data.get("message", "")
            page_context = data.get("pageContext", None)

            if not message:
                continue

            # Rate limit WebSocket messages
            if not _ws_rate_limiter.is_allowed(session_id):
                await websocket.send_json({
                    "type": "error",
                    "message": "Too many messages. Please slow down.",
                })
                continue

            await _handle_message(
                websocket, agent, repos, session_id, messages,
                message, page_context, visitor_id, conversation_summary,
            )

            # Periodic summarization (every 20 messages)
            if len(messages) > 0 and len(messages) % 20 == 0:
                asyncio.create_task(
                    _maybe_summarize(session_id, site, list(messages))
                )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error", error=str(e), error_type=type(e).__name__, session_id=session_id)
    finally:
        heartbeat_active = False
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

        try:
            await repos.chat_sessions.set_ended(session_id)
        except Exception as e:
            logger.warning("Failed to mark session ended", session_id=session_id, error=str(e))
        active_agents.pop(session_id, None)
        _ws_rate_limiter.cleanup(session_id)
        await repos.close()

        # Background: extract memories from this conversation
        if visitor_id and messages and len(messages) >= 4:
            asyncio.create_task(
                _extract_and_save_memories(visitor_id, site, session_id, list(messages))
            )


async def _handle_message(
    websocket: WebSocket,
    agent: ChatAgent,
    repos,
    session_id: str,
    messages: list[dict],
    message: str,
    page_context: dict | None,
    visitor_id: str | None = None,
    conversation_summary: str | None = None,
):
    """Process a single user message and stream the response."""
    messages.append({
        "role": "user",
        "content": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    await websocket.send_json({"type": "start"})

    full_response = ""
    try:
        async for token in agent.stream_response(
            message=message,
            page_context=page_context,
            repos=repos,
            visitor_id=visitor_id,
            conversation_summary=conversation_summary,
        ):
            full_response += token
            await websocket.send_json({"type": "token", "content": token})
    except Exception as e:
        logger.error("Chat stream error", error=str(e), error_type=type(e).__name__, session_id=session_id)
        await websocket.send_json({
            "type": "error",
            "message": "An error occurred. Please try again.",
        })
        full_response = "Sorry, an error occurred. Please try again."

    messages.append({
        "role": "assistant",
        "content": full_response,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    await repos.chat_sessions.update_messages(session_id, messages)

    await websocket.send_json({"type": "end"})


async def _extract_and_save_memories(visitor_id, site, session_id, messages):
    """Background task: extract and save visitor memories after session ends."""
    repos = await create_repos()
    try:
        extractor = MemoryExtractor()
        provider = get_llm_provider(site["llm_provider"], site["llm_model"])
        extracted = await extractor.extract_memories(messages, provider)

        for mem in extracted:
            await repos.visitor_memories.upsert(
                visitor_id=visitor_id,
                site_id=site["id"],
                key=mem["key"],
                data={
                    "category": mem["category"],
                    "value": mem["value"],
                    "confidence": mem.get("confidence", "medium"),
                    "source_session_id": session_id,
                },
            )
        if extracted:
            logger.info(
                "Memories extracted",
                count=len(extracted),
                visitor_id=visitor_id,
                session_id=session_id,
            )
    except Exception as e:
        logger.error("Memory extraction failed", error=str(e), session_id=session_id)
    finally:
        await repos.close()


async def _maybe_summarize(session_id, site, messages):
    """Background task: summarize long conversations."""
    repos = await create_repos()
    try:
        summarizer = ConversationSummarizer()
        if not await summarizer.should_summarize(messages):
            return

        existing = await repos.conversation_summaries.get_by_session(session_id)
        existing_text = existing["summary_text"] if existing else None

        provider = get_llm_provider(site["llm_provider"], site["llm_model"])
        summary_text, count = await summarizer.summarize(messages, provider, existing_text)

        if summary_text:
            await repos.conversation_summaries.upsert_by_session(
                session_id=session_id,
                data={
                    "site_id": site["id"],
                    "summary_text": summary_text,
                    "message_count_summarized": count,
                    "total_message_count": len(messages),
                },
            )
            logger.info("Conversation summarized", session_id=session_id, messages_summarized=count)
    except Exception as e:
        logger.error("Summarization failed", error=str(e), session_id=session_id)
    finally:
        await repos.close()
