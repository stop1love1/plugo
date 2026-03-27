import json
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from repositories import get_repos
from agent.core import ChatAgent

router = APIRouter()

# Store active agents per session
active_agents: dict[str, ChatAgent] = {}


@router.websocket("/ws/chat/{site_token}")
async def websocket_chat(websocket: WebSocket, site_token: str):
    """WebSocket endpoint for real-time chat streaming."""
    await websocket.accept()

    repos = await get_repos()

    # Find site by token
    site = await repos.sites.get_by_token(site_token)
    if not site:
        await websocket.send_json({"type": "error", "message": "Invalid site token"})
        await websocket.close()
        return

    # Create chat session
    chat_session = await repos.chat_sessions.create({"site_id": site["id"]})
    session_id = chat_session["id"]

    # Create agent
    agent = ChatAgent(
        site_id=site["id"],
        site_name=site["name"],
        site_url=site["url"],
        llm_provider=site["llm_provider"],
        llm_model=site["llm_model"],
    )
    active_agents[session_id] = agent

    # Send welcome
    await websocket.send_json({
        "type": "connected",
        "session_id": session_id,
        "greeting": site["greeting"],
        "config": {
            "primaryColor": site["primary_color"],
            "position": site["position"],
        },
    })

    messages = []

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            page_context = data.get("pageContext", None)

            if not message:
                continue

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
                await websocket.send_json({
                    "type": "error",
                    "message": f"Có lỗi xảy ra: {str(e)}",
                })
                full_response = "Xin lỗi, có lỗi xảy ra. Vui lòng thử lại."

            messages.append({
                "role": "assistant",
                "content": full_response,
                "timestamp": datetime.utcnow().isoformat(),
            })
            await repos.chat_sessions.update_messages(session_id, messages)

            await websocket.send_json({"type": "end"})

    except WebSocketDisconnect:
        await repos.chat_sessions.set_ended(session_id)
        active_agents.pop(session_id, None)
