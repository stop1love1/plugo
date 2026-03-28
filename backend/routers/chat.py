import json
import asyncio
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from repositories import get_repos
from agent.core import ChatAgent
from agent.memory import MemoryExtractor, ConversationSummarizer
from providers.factory import get_llm_provider
from logging_config import logger

router = APIRouter()

# Store active agents per session
active_agents: dict[str, ChatAgent] = {}


@router.websocket("/ws/chat/{site_token}")
async def websocket_chat(websocket: WebSocket, site_token: str):
    """WebSocket endpoint for real-time chat streaming.

    Supports session resumption: if the client sends a `session_id` in
    the first message, the server restores the previous conversation
    from the database instead of creating a new session.
    """
    await websocket.accept()

    repos = await get_repos()

    # Find site by token
    site = await repos.sites.get_by_token(site_token)
    if not site:
        await websocket.send_json({"type": "error", "message": "Invalid site token"})
        await websocket.close()
        return

    # Wait for the first message to check for session resumption
    # The client sends {"type": "init", "session_id": "...", "visitor_id": "..."} or just starts chatting
    first_data = await websocket.receive_json()

    session_id = None
    messages = []
    resumed = False
    visitor_id = first_data.get("visitor_id")

    # Check if client wants to resume an existing session
    if first_data.get("type") == "init" and first_data.get("session_id"):
        existing_session = await repos.chat_sessions.get_by_id(first_data["session_id"])
        if existing_session and existing_session.get("site_id") == site["id"] and not existing_session.get("ended_at"):
            session_id = existing_session["id"]
            messages = existing_session.get("messages", [])
            resumed = True
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

            await _handle_message(
                websocket, agent, repos, session_id, messages,
                message, page_context, visitor_id, conversation_summary,
            )

            # Periodic summarization (every 20 messages)
            if len(messages) > 0 and len(messages) % 20 == 0:
                asyncio.create_task(
                    _maybe_summarize(repos, session_id, site, messages)
                )

    except WebSocketDisconnect:
        heartbeat_active = False
        heartbeat_task.cancel()
        await repos.chat_sessions.set_ended(session_id)
        active_agents.pop(session_id, None)

        # Background: extract memories from this conversation
        if visitor_id and messages and len(messages) >= 4:
            asyncio.create_task(
                _extract_and_save_memories(repos, visitor_id, site, session_id, messages)
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
        "timestamp": datetime.utcnow().isoformat(),
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
        logger.error("Chat stream error", error=str(e), session_id=session_id)
        await websocket.send_json({
            "type": "error",
            "message": "An error occurred. Please try again.",
        })
        full_response = "Sorry, an error occurred. Please try again."

    messages.append({
        "role": "assistant",
        "content": full_response,
        "timestamp": datetime.utcnow().isoformat(),
    })
    await repos.chat_sessions.update_messages(session_id, messages)

    await websocket.send_json({"type": "end"})


async def _extract_and_save_memories(repos, visitor_id, site, session_id, messages):
    """Background task: extract and save visitor memories after session ends."""
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


async def _maybe_summarize(repos, session_id, site, messages):
    """Background task: summarize long conversations."""
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
