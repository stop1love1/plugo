from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from repositories import get_repos, Repositories
from auth import get_current_user, TokenData

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(
    site_id: str,
    page: int = 1,
    per_page: int = 20,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    return await repos.chat_sessions.list_by_site(site_id, page, per_page)


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
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
    site_token: Optional[str] = None,
):
    session = await repos.chat_sessions.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # If a site_token is provided, verify the session belongs to that site
    if site_token:
        site = await repos.sites.get_by_token(site_token)
        if not site or site.get("id") != session.get("site_id"):
            raise HTTPException(status_code=403, detail="Session does not belong to this site")

    messages = session.get("messages", [])
    if data.message_index >= len(messages):
        raise HTTPException(status_code=400, detail="Invalid message index")
    messages[data.message_index]["feedback"] = data.rating
    await repos.chat_sessions.update_messages(session_id, messages)
    return {"message": "Feedback recorded"}
