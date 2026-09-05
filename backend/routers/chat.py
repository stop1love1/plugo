import asyncio
import contextlib
import re
import uuid
from datetime import UTC, datetime
from time import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agent.core import ChatAgent
from agent.memory import ConversationSummarizer, MemoryExtractor, trim_messages_for_context
from logging_config import logger
from providers.factory import get_llm_provider
from repositories import create_repos
from utils.cors import validate_site_origin
from utils.pricing import estimate_cost
from utils.rate_limit import SiteTokenWSRateLimiter, get_ws_ip_ceiling, ws_client_ip

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
# Two stacked limits, mirroring the pair the public HTTP routes carry (see the
# `utils/rate_limit.py` module docstring):
#   * per (site_token, session) — tenant fairness, the limiter below;
#   * per peer address — the abuse ceiling. It lives in utils/rate_limit.py because
#     it has to outlive any one connection: both halves of the per-session key are
#     client-supplied, so a reconnect mints a fresh bucket and that limiter alone
#     never binds across connections.
# A message must satisfy both. The per-session window is checked first, so a message
# it already refused doesn't spend the address's ceiling.
WS_RATE_LIMIT_WINDOW = 60  # seconds
WS_RATE_LIMIT_MAX = 20  # max messages per window

_ws_rate_limiter = SiteTokenWSRateLimiter(window_seconds=WS_RATE_LIMIT_WINDOW, max_requests=WS_RATE_LIMIT_MAX)

# One refusal frame for both limits: which bucket filled up is the server's business,
# and the client's remedy ("slow down") is the same either way.
WS_RATE_LIMITED_MESSAGE = "Too many messages. Please slow down."

# Ceiling on the page body a client can push into the system prompt. Shared with the SSE
# transport, which imports it from here (the import only goes chat -> chat_sse's way).
MAX_PAGE_TEXT_CHARS = 5000


def _clamp_page_context(page_context: dict | None) -> dict | None:
    """Bound the page body a client can push into the system prompt.

    The body travels under ``pageText``: that is the key the widget fills
    (``frontend/src/widget/index.ts``), the key ``docs/api-reference.md`` documents, and
    the only one ``ChatAgent._build_system_prompt`` reads. An earlier clamp on ``"text"``
    bounded a key nothing writes and nothing reads, so it never truncated anything while
    reading as if the page body were bounded.

    Returns a shallow copy when a clamp applies; the caller's request model is left alone.
    """
    if not isinstance(page_context, dict):
        return None
    page_text = page_context.get("pageText")
    if isinstance(page_text, str) and len(page_text) > MAX_PAGE_TEXT_CHARS:
        return {**page_context, "pageText": page_text[:MAX_PAGE_TEXT_CHARS]}
    return page_context


def crossed_multiple(before: int, after: int, step: int) -> bool:
    """Did the stored message count move past a multiple of ``step`` on this turn?

    Asked instead of ``after % step == 0`` because a stored count can go odd and stay odd:
    a turn whose provider streams nothing leaves the visitor's message in the list without
    a reply (``_handle_message`` appends it unconditionally but persists only non-empty
    output), so every later count on that session is off by one. An exact-landing test
    would then never fire again for the rest of the session's life — not a skipped beat
    but a permanent one, which for summarization means the prompt grows unbounded forever.
    """
    return before // step < after // step


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


def restore_agent_history(agent: ChatAgent, stored_messages: list[dict], summary_row: dict | None) -> None:
    """Replay persisted history into the agent's LLM-facing message list.

    When a summary already covers the older part of the conversation, only the tail the
    summary leaves out is replayed: the summary itself goes into the system prompt, and
    replaying what it replaces is exactly what made this feature grow the prompt instead
    of shrinking it.

    How far a summary reaches is whatever the pass that wrote it covered, recorded on the
    row as ``message_count_summarized``. Summarization fires every 20 stored messages, so
    a session can close with up to 19 more than the last pass took in — those must still
    be replayed, or they end up in neither the summary nor the agent.

    ``stored_messages`` is never mutated — the persisted session record keeps everything
    for the dashboard's Chat Log and the analytics endpoints.
    """
    history = stored_messages
    if summary_row and summary_row.get("summary_text"):
        covered = int(summary_row.get("message_count_summarized") or 0)
        keep_recent = max(ConversationSummarizer.KEEP_RECENT_MESSAGES, len(stored_messages) - covered)
        history = trim_messages_for_context(stored_messages, keep_recent)
    for msg in history:
        # Tolerate a stored message missing either key: a malformed row should replay as
        # empty, not abort the visitor's turn with a KeyError mid-request.
        role = "user" if msg.get("role") == "user" else "assistant"
        agent.messages.append({"role": role, "content": msg.get("content", "")})


def build_assistant_message(content: str, tool_calls: list[dict] | None) -> dict:
    """Assemble the assistant message both transports persist after a turn.

    ``tool_calls`` is copied (not referenced) when non-empty, so a later turn resetting the
    agent's accumulator can't mutate what was already persisted. Omitted entirely when
    nothing ran — that absence is exactly what a legacy session, or an ordinary turn with no
    tool call, looks like to the analytics reader.
    """
    message: dict = {
        "role": "assistant",
        "content": content,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if tool_calls:
        message["tool_calls"] = list(tool_calls)
    return message


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
    # Read once: the peer address is fixed for the life of the connection, and it is
    # the only rate-limit dimension this client didn't choose for itself.
    client_ip = ws_client_ip(websocket)
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
        await websocket.send_json(
            {"type": "error", "message": "This chat is not available yet. Please try again later."}
        )
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
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", str(raw_visitor_id))[:64] if raw_visitor_id else ""
    # Whether this id is one the *client* holds, or one we minted for this connection alone.
    # Mirrors chat_sse.py's visitor_is_addressable: the fallback uuid below never reaches the
    # visitor, so no later connection can present it back — memories keyed by it would be rows
    # nothing ever reads again, and extraction is a billed LLM round trip. An unaddressable
    # visitor gets no session-end extraction (see the dispatch in the `finally` block below).
    # Everything else (the stored session, the prompt) still uses the id.
    visitor_is_addressable = bool(sanitized)
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
                    # `visitor_id` is never falsy by this point (the uuid4() fallback above
                    # guarantees that), so a branch here inheriting `existing_session`'s stored
                    # visitor_id would never run. Deliberately not made live either: the SSE
                    # fix established that inheriting a stored id is the wrong fix on its own,
                    # because the session row can itself hold a minted throwaway id — inheriting
                    # would hand back exactly the unreachable id this fix removes, and an
                    # inherited id is indistinguishable from a client-supplied one at the
                    # `visitor_is_addressable` gate above. This connection's own sanitized input
                    # is what decides addressability, not what a prior connection happened to
                    # store.
                    logger.info("Session resumed", session_id=session_id, message_count=len(messages))

        # Create new session if not resuming. `visitor_id` is never falsy here (the
        # uuid4() fallback above guarantees that), so this always stores one.
        if not session_id:
            session_data = {"site_id": site["id"], "visitor_id": visitor_id}
            chat_session = await repos.chat_sessions.create(session_data)
            session_id = chat_session["id"]

        # Fetch conversation summary for resumed sessions. Read before the replay
        # below, which the summary bounds.
        conversation_summary = None
        summary_row = None
        if resumed:
            try:
                summary_row = await repos.conversation_summaries.get_by_session(session_id)
                if summary_row:
                    conversation_summary = summary_row["summary_text"]
            except Exception:
                pass  # conversation_summaries repo may not exist yet

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
            restore_agent_history(agent, messages, summary_row)

        active_agents[session_id] = agent

    # Send welcome with session info and previous messages
    await websocket.send_json(
        {
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
        }
    )

    # If the first message was a chat message (not init), process it
    if first_data.get("type") != "init" and first_data.get("message"):
        first_message = first_data.get("message", "")
        # Mirror the turn-loop size guard so a huge first message can't bypass it.
        if len(first_message) > 10000:
            await websocket.close(code=1008, reason="Message too long")
            return
        # The per-address ceiling covers this message too. Without it a client could
        # carry one message per connection and never reach the turn loop's check at
        # all — the exact reconnect bypass the ceiling exists to close.
        #
        # The per-session window is deliberately not applied here. It could never
        # *refuse* a first message — this connection's bucket is necessarily empty,
        # a resumed session's having been dropped at the previous disconnect — but
        # skipping it also means this message never *consumes* a slot, so a client
        # using this path gets 21 messages per connection against a 20-message
        # window. That is pre-existing behaviour and costs nothing in abuse terms
        # (the ceiling counts this message either way); it is one extra message of
        # slack in the fairness window, not a hole in the ceiling.
        if not get_ws_ip_ceiling().is_allowed(client_ip):
            await websocket.send_json({"type": "error", "message": WS_RATE_LIMITED_MESSAGE})
        else:
            await _handle_message(
                websocket,
                agent,
                repos,
                session_id,
                messages,
                first_message,
                _clamp_page_context(first_data.get("pageContext")),
                visitor_id,
                conversation_summary,
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
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Message too long. Please keep it under 10,000 characters.",
                    }
                )
                continue

            page_context = _clamp_page_context(page_context)

            # Rate limit WebSocket messages: the per-(site_token, session) window
            # first, then the per-address ceiling a reconnect can't reset.
            if not _ws_rate_limiter.is_allowed(session_id, site_token) or not get_ws_ip_ceiling().is_allowed(client_ip):
                await websocket.send_json({"type": "error", "message": WS_RATE_LIMITED_MESSAGE})
                continue

            # Swap in a summary the background summarizer finished while we were taking
            # messages: it goes into the system prompt and the history it covers leaves
            # the agent. Done here — between turns, with no await in between — so the
            # trim can never run under an in-flight provider call.
            staged_summary = agent.apply_staged_summary()
            if staged_summary:
                conversation_summary = staged_summary

            # Captured *before* the call: `_handle_message` mutates `messages` in place,
            # appending this turn's visitor message (always) and its reply (only when the
            # provider produced one). Reading the length afterwards would leave nothing to
            # compare the crossing against.
            stored_before = len(messages)

            await _handle_message(
                websocket,
                agent,
                repos,
                session_id,
                messages,
                message,
                page_context,
                visitor_id,
                conversation_summary,
            )

            # Periodic summarization — every 20 messages, asked as "did this turn cross a
            # multiple?" rather than "did it land on one". See `crossed_multiple`: a turn
            # that streamed nothing makes the count odd for good, and an exact-landing test
            # would silently disable summarization for that session from then on.
            if crossed_multiple(stored_before, len(messages), ConversationSummarizer.MESSAGE_THRESHOLD):
                # Read the boundary here, on this task, so it lines up with the snapshot
                # handed to the summarizer; anything appended while it runs stays.
                _fire_and_forget(
                    _maybe_summarize(
                        session_id,
                        site,
                        list(messages),
                        agent,
                        agent.summary_boundary(ConversationSummarizer.KEEP_RECENT_MESSAGES),
                    )
                )

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
        # Only the per-session bucket is dropped. The per-address ceiling is left to
        # expire on its own clock: cleaning it up here would hand every reconnect a
        # fresh allowance, which is precisely what it exists to prevent.
        _ws_rate_limiter.cleanup(session_id, site_token)
        await repos.close()

        # Background: extract memories from this conversation. Skipped for a minted visitor
        # id: see visitor_is_addressable above — the extraction would still cost a full LLM
        # round trip, and would write visitor_memories rows under a key no later connection
        # can present.
        if visitor_is_addressable and messages and len(messages) >= 4:
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
    messages.append(
        {
            "role": "user",
            "content": message,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )

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
        logger.error(
            "Chat stream error: {error_type}: {error}", error=str(e), error_type=type(e).__name__, session_id=session_id
        )
        try:
            await websocket.send_json({"type": "error", "message": "Oops, something went wrong. Please try again."})
        except Exception:
            stream_error = True
        if not full_response:
            full_response = "Oops, something went wrong. Please try again."

    # Only save complete responses (skip if client disconnected with no content)
    if full_response.strip():
        # Structured tool-invocation record for this turn (analytics reads it).
        messages.append(build_assistant_message(full_response, agent.last_tool_calls))
        try:
            await repos.chat_sessions.update_messages(session_id, messages)
        except Exception as e:
            logger.error("Failed to save messages", session_id=session_id, error=str(e))

    # Emit structured citations (if any) BEFORE the end marker so the client
    # can attach them to the just-finished assistant message.
    if not stream_error and agent.last_citations:
        with contextlib.suppress(Exception):
            await websocket.send_json(
                {
                    "type": "citations",
                    "items": agent.last_citations,
                }
            )

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


async def _maybe_summarize(
    session_id: str,
    site: dict,
    messages: list[dict],
    agent: ChatAgent | None = None,
    trim_boundary: dict | None = None,
) -> None:
    """Background task: summarize long conversations.

    ``messages`` is a snapshot of the persisted history taken at dispatch time, and
    ``trim_boundary`` (from ``ChatAgent.summary_boundary``) is the matching point in the
    live agent's history. When an ``agent`` is given the finished summary is staged on it
    along with that boundary, so the next turn sends the summary in place of the history
    it covers (see ``ChatAgent.apply_staged_summary``).
    """
    repos = await create_repos()
    try:
        summarizer = ConversationSummarizer()
        if not await summarizer.should_summarize(messages):
            return

        existing = await repos.conversation_summaries.get_by_session(session_id)
        existing_text = existing["summary_text"] if existing else None

        provider = get_llm_provider(site["llm_provider"], site["llm_model"])
        summary_text, count = await summarizer.summarize(messages, provider, existing_text)

        # `count` is 0 on the two paths that produced no new coverage: nothing left to
        # summarize, and the exception handler, which carries the *existing* text back out.
        # Upserting on the text alone would then rewrite a correct `message_count_summarized`
        # with 0, recording less reach than the stored summary actually has.
        if summary_text and count:
            await repos.conversation_summaries.upsert_by_session(
                session_id=session_id,
                data={
                    "site_id": site["id"],
                    "summary_text": summary_text,
                    "message_count_summarized": count,
                    "total_message_count": len(messages),
                },
            )
            # Only sets an attribute — the trim itself happens on the transport's task.
            if agent is not None:
                agent.stage_summary(summary_text, trim_boundary)
            logger.info("Conversation summarized", session_id=session_id, messages_summarized=count)
    except Exception as e:
        logger.error("Summarization failed", error=str(e), session_id=session_id)
    finally:
        await repos.close()
