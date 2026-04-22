"""Server-Sent Events streaming endpoint for chat.

A simpler alternative to the `/ws/chat/...` WebSocket for iframe embeds and
serverless clients that can't keep a bidirectional socket open. Unlike the WS
flow, SSE is stateless: each request creates a transient agent with history
loaded from DB and is NOT registered in `active_agents` — multiple concurrent
SSE requests on the same session are independent.

Events emitted (per the EventSource spec):
    event: token       data: <plain text>
    event: citations   data: <JSON {"items": [...]}>
    event: done        data: <JSON {"session_id": "..."}>
    event: error       data: <JSON {"message": "..."}>
"""

import contextlib
import json
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agent.core import ChatAgent
from config import settings
from logging_config import logger
from repositories import Repositories, get_repos
from routers.chat import get_cached_site
from utils.cors import validate_site_origin
from utils.pricing import estimate_cost
from utils.rate_limit import acquire_sse_slot, release_sse_slot, site_token_key

router = APIRouter()


class ChatSSERequest(BaseModel):
    message: str
    session_id: str | None = None
    visitor_id: str | None = None
    page_context: dict | None = None


# Lazy limiter lookup so we stay decoupled from main.py import order.
def _limiter():
    from main import limiter
    return limiter


# Per-site-token rate limit. This decorator is applied after the router
# definition so the module can import cleanly; main.limiter already exists
# by the time the first request hits us.
async def _chat_stream_core(
    site_token: str,
    body: ChatSSERequest,
    request: Request,
    repos: Repositories,
):
    site = await get_cached_site(repos, site_token)
    if not site:
        raise HTTPException(status_code=404, detail="Invalid site token")
    if not site.get("is_approved"):
        raise HTTPException(status_code=403, detail="Site not approved")

    origin = request.headers.get("origin", "")
    # Per-site tenant isolation: the global CORS middleware can't enforce this
    # because it knows nothing about which site_token the request targets.
    if not validate_site_origin(site, origin):
        raise HTTPException(status_code=403, detail="Origin not allowed")

    # Sanitize visitor_id exactly like the WS path so attackers can't inject
    # control chars / unicode / oversized strings into the stored field or the
    # downstream agent-memory lookup key. Scope to site to block cross-site
    # spoofing.
    raw_visitor_id = body.visitor_id or ""
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', str(raw_visitor_id))[:64] if raw_visitor_id else ""
    if not sanitized:
        sanitized = str(uuid.uuid4())
    visitor_id = f"{site['id']}:{sanitized}"

    session_id = body.session_id
    history_messages: list[dict] = []
    if session_id:
        existing = await repos.chat_sessions.get_by_id(session_id)
        if existing and existing.get("site_id") == site["id"]:
            history_messages = list(existing.get("messages") or [])
        else:
            session_id = None
    if not session_id:
        session_data: dict = {"site_id": site["id"], "visitor_id": visitor_id}
        created = await repos.chat_sessions.create(session_data)
        session_id = created["id"]

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
    for m in history_messages:
        role = "user" if m.get("role") == "user" else "assistant"
        agent.messages.append({"role": role, "content": m.get("content", "")})

    async def event_stream() -> AsyncIterator[dict]:
        # Always persist whatever we streamed — on normal completion, on
        # exception, and on client disconnect (sse-starlette raises
        # GeneratorExit, which `except Exception` does NOT catch). Wrap in
        # try/finally so save + token-usage run on any exit path.
        full_response = ""
        streamed_ok = False
        try:
            async for tok in agent.stream_response(
                message=body.message,
                page_context=body.page_context,
                repos=repos,
                visitor_id=visitor_id,
            ):
                full_response += tok
                yield {"event": "token", "data": tok}

            if agent.last_citations:
                yield {
                    "event": "citations",
                    "data": json.dumps({"items": agent.last_citations}),
                }

            yield {"event": "done", "data": json.dumps({"session_id": session_id})}
            streamed_ok = True
        except Exception as e:
            logger.error("SSE stream error", session_id=session_id, error=str(e))
            # Best-effort error event — safe to ignore if the client is gone.
            with contextlib.suppress(Exception):
                yield {"event": "error", "data": json.dumps({"message": "Stream failed"})}
        finally:
            # Persist only if we actually got some output. Mirrors the WS path.
            if full_response.strip():
                history_messages.append({
                    "role": "user",
                    "content": body.message,
                    "timestamp": datetime.now(UTC).isoformat(),
                })
                history_messages.append({
                    "role": "assistant",
                    "content": full_response,
                    "timestamp": datetime.now(UTC).isoformat(),
                })
                try:
                    await repos.chat_sessions.update_messages(session_id, history_messages)
                except Exception as e:
                    logger.error("SSE: save messages failed", session_id=session_id, error=str(e))

                usage = agent.total_usage
                if usage:
                    in_t = int(usage.get("input_tokens") or 0)
                    out_t = int(usage.get("output_tokens") or 0)
                    if in_t or out_t:
                        cost = estimate_cost(agent.llm_model, in_t, out_t)
                        try:
                            await repos.chat_sessions.add_token_usage(
                                session_id, in_t, out_t, cost
                            )
                        except Exception as e:
                            logger.warning(
                                "SSE: record token usage failed",
                                session_id=session_id, error=str(e),
                            )
            # Release the concurrent-stream slot acquired by the endpoint.
            await release_sse_slot(site_token)
            if not streamed_ok:
                logger.info(
                    "SSE stream ended without clean done event",
                    session_id=session_id,
                    bytes_streamed=len(full_response),
                )

    return EventSourceResponse(event_stream())


def register_routes() -> APIRouter:
    """Attach the limiter decorator at include-time (after main.py created the limiter).

    Using a factory here lets us use the configured per-site-token key without
    importing main at module-load time (which would be circular).
    """
    limiter = _limiter()

    @router.post("/api/chat/{site_token}/stream")
    @limiter.limit(settings.rate_limit_chat, key_func=site_token_key)
    async def chat_stream(
        site_token: str,
        body: ChatSSERequest,
        request: Request,
        repos: Repositories = Depends(get_repos),
    ):
        # Cap simultaneous open streams per token — slowapi's per-window limit
        # doesn't account for long-lived connections. Slot is released in the
        # event_stream generator's finally (normal exit, error, or client
        # disconnect). On any synchronous failure path below we release
        # explicitly so we don't leak slots.
        if not await acquire_sse_slot(site_token):
            raise HTTPException(status_code=429, detail="Too many concurrent streams")
        try:
            return await _chat_stream_core(site_token, body, request, repos)
        except Exception:
            # _chat_stream_core raised before returning EventSourceResponse
            # (e.g. 404/403) — the generator's finally will never run, so
            # release here to balance the acquire.
            await release_sse_slot(site_token)
            raise

    return router
