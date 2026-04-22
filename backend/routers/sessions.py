
from auth import TokenData, get_current_user
from fastapi import APIRouter, Depends, Header, HTTPException
from logging_config import logger
from pydantic import BaseModel, Field

from repositories import Repositories, get_repos

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _extract_bearer_token(authorization: str | None) -> str | None:
    """Return the token from an `Authorization: Bearer <token>` header, or None."""
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None


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
    authorization: str | None = Header(default=None),
    site_token: str | None = None,
):
    """Widget feedback submission.

    Site token is read from the ``Authorization: Bearer <site_token>`` header.
    The legacy ``?site_token=...`` query param is still accepted for one release
    cycle; using it logs a deprecation warning so we can remove it safely.
    """
    session = await repos.chat_sessions.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    header_token = _extract_bearer_token(authorization)
    resolved_token = header_token or site_token
    if site_token and not header_token:
        logger.warning(
            "Deprecated feedback site_token query param used",
            session_id=session_id,
        )

    if resolved_token:
        site = await repos.sites.get_by_token(resolved_token)
        if not site or site.get("id") != session.get("site_id"):
            raise HTTPException(status_code=403, detail="Session does not belong to this site")

    messages = session.get("messages", [])
    if data.message_index >= len(messages):
        raise HTTPException(status_code=400, detail="Invalid message index")
    messages[data.message_index]["feedback"] = data.rating
    await repos.chat_sessions.update_messages(session_id, messages)
    return {"message": "Feedback recorded"}
