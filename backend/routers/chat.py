import asyncio
import contextlib
import re
import uuid
from datetime import UTC, datetime
from time import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from logging_config import logger
from utils.cors import validate_site_origin
from utils.pricing import estimate_cost
from utils.rate_limit import SiteTokenWSRateLimiter

from agent.core import ChatAgent
from agent.memory import ConversationSummarizer, MemoryExtractor
from providers.factory import get_llm_provider
from repositories import create_repos

router = APIRouter()

# Store active agents per session
active_agents: dict[str, ChatAgent] = {}

# Per-session locks to serialize the resume check + active_agents insert.
# Bounded to keep memory in check for long-lived servers; we drop unheld locks
# once we exceed the cap, since a fresh Lock will be created next time it's needed.
_session_resume_locks: dict[str, asyncio.Lock] = {}
_SESSION_LOCKS_MAX = 1000


def _get_session_resume_lock(session_id: str) -> asyncio.Lock:
    """Return (creating if needed) a Lock for this session_id. Drops unheld locks
    when the registry exceeds _SESSION_LOCKS_MAX entries."""
    lock = _session_resume_locks.get(session_id)
    if lock is None:
        if len(_session_resume_locks) >= _SESSION_LOCKS_MAX:
            stale = [k for k, v in _session_resume_locks.items() if not v.locked()]
            for k in stale[: max(1, len(stale) // 2)]:
                _session_resume_locks.pop(k, None)
        lock = asyncio.Lock()
        _session_resume_locks[session_id] = lock
    return lock

# Retain references until background tasks complete (RUF006 / asyncio.create_task)
_background_tasks: set[asyncio.Task] = set()


def _fire_and_forget(coro):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

# --- WebSocket rate limiting ---
# Bucket per (site_token, session) so one tenant's traffic can't starve another's.
WS_RATE_LIMIT_WINDOW = 60  # seconds
WS_RATE_LIMIT_MAX = 20  # max messages per window

_ws_rate_limiter = SiteTokenWSRateLimiter(
    window_seconds=WS_RATE_LIMIT_WINDOW, max_requests=WS_RATE_LIMIT_MAX
)

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


@router.websocket("/ws/chat")
async def websocket_chat_init(websocket: WebSocket):
    """WebSocket chat endpoint — site_token is read from the first `init` message.

    Prefer this endpoint over the legacy path-based variant; it keeps the token out
    of URL access logs and proxies. Flow:
        1. Client connects.
        2. Client sends `{ "type": "init", "site_token": "...", ... }` as first message.
        3. Server validates the token and replies with the usual `connected` frame.
    """
    await websocket.accept()
    repos = await create_repos()

    try:
        first_data = await websocket.receive_json()
    except Exception:
        await websocket.close(code=4401, reason="Missing init message")
        await repos.close()
        return

    site_token = first_data.get("site_token") if isinstance(first_data, dict) else None
    if not site_token or not isinstance(site_token, str):
        await websocket.close(code=4401, reason="Missing site_token in init")
        await repos.close()
        return

    site = await get_cached_site(repos, site_token)
    if not site:
        await websocket.send_json({"type": "error", "message": "Invalid site token"})
        await websocket.close(code=4401, reason="Invalid site token")
        await repos.close()
        return

    await _run_websocket_chat(websocket, repos, site, site_token, first_data=first_data)


@router.websocket("/ws/chat/{site_token}")
async def websocket_chat(websocket: WebSocket, site_token: str):
    """DEPRECATED WebSocket endpoint — site_token in URL path.

    Prefer `/ws/chat` (token in init message). This route stays live for one
    release cycle to avoid breaking pinned widget bundles; each connection logs
    a deprecation warning.
    """
    logger.warning(
        "Deprecated WS route /ws/chat/{site_token} used — prefer init-message auth",
        origin=websocket.headers.get("origin", "<none>"),
    )
    await websocket.accept()

    repos = await create_repos()

    # Find site by token (cached)
    site = await get_cached_site(repos, site_token)
    if not site:
        await websocket.send_json({"type": "error", "message": "Invalid site token"})
        await websocket.close()
        return

    await _run_websocket_chat(websocket, repos, site, site_token, first_data=None)


async def _run_websocket_chat(
    websocket: WebSocket,
    repos,
    site: dict,
    site_token: str,
    first_data: dict | None,
) -> None:
    """Shared WS chat body used by both the legacy path-based and the new init-message routes."""
    # Validate WebSocket origin against site's allowed_domains.
    # Per-site tenant isolation — the global CORS middleware is a site-agnostic
    # allowlist and can't enforce this; see utils/cors.py for contract.
    origin = websocket.headers.get("origin", "")
    if site.get("allowed_domains") and not validate_site_origin(site, origin):
        reason = "Origin required" if not origin else "Origin not allowed"
        # SSE returns 403 (visible in access logs); WS closing silently would
        # be a monitoring blind spot. Log each rejection with its reason.
        logger.warning(
            "WS origin rejected",
            site_id=site.get("id"),
            origin=origin or "<none>",
            reason=reason,
        )
        await websocket.close(code=4003, reason=reason)
        return

    if not site.get("is_approved"):
        await websocket.send_json({"type": "error", "message": "This chat is not available yet. Please try again later."})
        await websocket.close()
        return

    # Wait for the first message to check for session resumption unless the caller
    # already consumed it (the /ws/chat init-message route reads it to extract
    # the site_token and passes it down).
    if first_data is None:
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

    # Serialize resume checks + active_agents insert so two concurrent clients can't
    # both pass the ended_at window and both become "live" for the same session.
    # Only acquire a lock on the resume path — a new-connection path doesn't need
    # serialization and would just pollute the lock registry with unique keys.
    requested_resume_id = first_data.get("session_id") if first_data.get("type") == "init" else None
    resume_lock = _get_session_resume_lock(requested_resume_id) if requested_resume_id else contextlib.nullcontext()
    async with resume_lock:
        # Check if client wants to resume an existing session
        if requested_resume_id:
            if requested_resume_id in active_agents:
                # Another WS is already live for this session — reject to prevent interleaved streams.
                # Use try/finally so repos.close() always runs even if websocket.close() raises.
                try:
                    await websocket.close(code=4409, reason="Session already active")
                finally:
                    await repos.close()
                return
            existing_session = await repos.chat_sessions.get_by_id(requested_resume_id)
            if existing_session and existing_session.get("site_id") == site["id"]:
                # Allow resume if session is still open OR ended less than 5 minutes ago
                ended_at = existing_session.get("ended_at")
                can_resume = not ended_at
                if ended_at and isinstance(ended_at, str):
                    try:
                        ended_time = datetime.fromisoformat(ended_at)
                        if ended_time.tzinfo is None:
                            ended_time = ended_time.replace(tzinfo=UTC)
                        can_resume = (datetime.now(UTC) - ended_time).total_seconds() < 300
                    except ValueError:
                        pass
                elif ended_at and isinstance(ended_at, datetime):
                    if ended_at.tzinfo is None:
                        ended_at = ended_at.replace(tzinfo=UTC)
                    can_resume = (datetime.now(UTC) - ended_at).total_seconds() < 300

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
            system_prompt=site.get("system_prompt", ""),
            bot_rules=site.get("bot_rules", ""),
            response_language=site.get("response_language", "auto"),
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
        first_message = first_data.get("message", "")
        # Mirror the turn-loop size guard so a huge first message can't bypass it.
        if len(first_message) > 10000:
            await websocket.close(code=1008, reason="Message too long")
            return
        await _handle_message(
            websocket, agent, repos, session_id, messages,
            first_message, first_data.get("pageContext"),
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

            # Validate message size limits
            if len(message) > 10000:
                await websocket.send_json({
                    "type": "error",
                    "message": "Message too long. Please keep it under 10,000 characters.",
                })
                continue

            if page_context and isinstance(page_context, dict):
                page_text = page_context.get("text", "")
                if isinstance(page_text, str) and len(page_text) > 5000:
                    page_context["text"] = page_text[:5000]

            # Rate limit WebSocket messages — bucket per (site_token, session)
            if not _ws_rate_limiter.is_allowed(session_id, site_token):
                await websocket.send_json({
                    "type": "error",
                    "message": "Too many messages. Please slow down.",
                })
                continue

            # Re-fetch conversation summary periodically (after summarization may have run)
            if len(messages) > 0 and len(messages) % 20 == 0:
                try:
                    existing_summary = await repos.conversation_summaries.get_by_session(session_id)
                    if existing_summary:
                        conversation_summary = existing_summary["summary_text"]
                except Exception:
                    pass

            await _handle_message(
                websocket, agent, repos, session_id, messages,
                message, page_context, visitor_id, conversation_summary,
            )

            # Periodic summarization (every 20 messages)
            if len(messages) > 0 and len(messages) % 20 == 0:
                _fire_and_forget(_maybe_summarize(session_id, site, list(messages)))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error", error=str(e), error_type=type(e).__name__, session_id=session_id)
    finally:
        heartbeat_active = False
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task

        try:
            await repos.chat_sessions.set_ended(session_id)
        except Exception as e:
            logger.warning("Failed to mark session ended", session_id=session_id, error=str(e))
        active_agents.pop(session_id, None)
        _ws_rate_limiter.cleanup(session_id, site_token)
        await repos.close()

        # Background: extract memories from this conversation
        if visitor_id and messages and len(messages) >= 4:
            _fire_and_forget(_extract_and_save_memories(visitor_id, site, session_id, list(messages)))


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
        "timestamp": datetime.now(UTC).isoformat(),
    })

    await websocket.send_json({"type": "start"})

    full_response = ""
    stream_error = False
    try:
        async for token in agent.stream_response(
            message=message,
            page_context=page_context,
            repos=repos,
            visitor_id=visitor_id,
            conversation_summary=conversation_summary,
        ):
            full_response += token
            try:
                await websocket.send_json({"type": "token", "content": token})
            except Exception:
                # Client disconnected mid-stream — stop generating but keep what we have
                stream_error = True
                break
    except TimeoutError:
        logger.warning("Chat stream timeout", session_id=session_id)
        full_response += "\n\n⚠️ Response timed out."
        try:
            await websocket.send_json({"type": "error", "message": "Sorry, that took too long. Please try again."})
        except Exception:
            stream_error = True
    except Exception as e:
        logger.error("Chat stream error: {error_type}: {error}", error=str(e), error_type=type(e).__name__, session_id=session_id)
        try:
            await websocket.send_json({"type": "error", "message": "Oops, something went wrong. Please try again."})
        except Exception:
            stream_error = True
        if not full_response:
            full_response = "Oops, something went wrong. Please try again."

    # Only save complete responses (skip if client disconnected with no content)
    if full_response.strip():
        messages.append({
            "role": "assistant",
            "content": full_response,
            "timestamp": datetime.now(UTC).isoformat(),
        })
        try:
            await repos.chat_sessions.update_messages(session_id, messages)
        except Exception as e:
            logger.error("Failed to save messages", session_id=session_id, error=str(e))

    # Emit structured citations (if any) BEFORE the end marker so the client
    # can attach them to the just-finished assistant message.
    if not stream_error and agent.last_citations:
        with contextlib.suppress(Exception):
            await websocket.send_json({
                "type": "citations",
                "items": agent.last_citations,
            })

    # Record token usage for this turn (providers without usage reporting are no-ops).
    usage = agent.total_usage
    if usage:
        in_t = int(usage.get("input_tokens") or 0)
        out_t = int(usage.get("output_tokens") or 0)
        if in_t or out_t:
            cost = estimate_cost(agent.llm_model, in_t, out_t)
            try:
                await repos.chat_sessions.add_token_usage(session_id, in_t, out_t, cost)
            except Exception as e:
                logger.warning("Failed to record token usage", session_id=session_id, error=str(e))

    if not stream_error:
        with contextlib.suppress(Exception):
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
