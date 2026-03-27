import json
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from repositories import get_repos
from agent.core import ChatAgent
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
    # The client sends {"type": "init", "session_id": "..."} or just starts chatting
    first_data = await websocket.receive_json()

    session_id = None
    messages = []
    resumed = False

    # Check if client wants to resume an existing session
    if first_data.get("type") == "init" and first_data.get("session_id"):
        existing_session = await repos.chat_sessions.get_by_id(first_data["session_id"])
        if existing_session and existing_session.get("site_id") == site["id"] and not existing_session.get("ended_at"):
            session_id = existing_session["id"]
            messages = existing_session.get("messages", [])
            resumed = True
            logger.info("Session resumed", session_id=session_id, message_count=len(messages))

    # Create new session if not resuming
    if not session_id:
        chat_session = await repos.chat_sessions.create({"site_id": site["id"]})
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
    })

    # If the first message was a chat message (not init), process it
    if first_data.get("type") != "init" and first_data.get("message"):
        await _handle_message(
            websocket, agent, repos, session_id, messages,
            first_data["message"], first_data.get("pageContext"),
        )

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            page_context = data.get("pageContext", None)

            if not message:
                continue

            await _handle_message(
                websocket, agent, repos, session_id, messages,
                message, page_context,
            )

    except WebSocketDisconnect:
        await repos.chat_sessions.set_ended(session_id)
        active_agents.pop(session_id, None)


async def _handle_message(
    websocket: WebSocket,
    agent: ChatAgent,
    repos,
    session_id: str,
    messages: list[dict],
    message: str,
    page_context: dict | None,
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
