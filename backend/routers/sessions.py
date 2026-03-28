from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Optional
from repositories import get_repos, Repositories

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(
    site_id: str,
    page: int = 1,
    per_page: int = 20,
    repos: Repositories = Depends(get_repos),
):
    return await repos.chat_sessions.list_by_site(site_id, page, per_page)


@router.get("/{session_id}")
async def get_session(session_id: str, repos: Repositories = Depends(get_repos)):
    session = await repos.chat_sessions.get_by_id(session_id)
    if not session:
        return {"error": "Session not found"}
    return session


class FeedbackRequest(BaseModel):
    message_index: int = Field(ge=0)
    rating: str = Field(pattern="^(up|down)$")


@router.post("/{session_id}/feedback")
async def submit_feedback(
    session_id: str,
    data: FeedbackRequest,
    repos: Repositories = Depends(get_repos),
):
    session = await repos.chat_sessions.get_by_id(session_id)
    if not session:
        return {"error": "Session not found"}
    messages = session.get("messages", [])
    if data.message_index >= len(messages):
        return {"error": "Invalid message index"}
    messages[data.message_index]["feedback"] = data.rating
    await repos.chat_sessions.update_messages(session_id, messages)
    return {"message": "Feedback recorded"}
