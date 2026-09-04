from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import TokenData, get_current_user
from config import settings
from limiter import limiter
from logging_config import logger
from repositories import Repositories, get_repos
from utils.rate_limit import extract_bearer_token, site_token_key

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# Upper bound on page size so a client can't request an unbounded result set.
MAX_PER_PAGE = 100


@router.get("")
async def list_sessions(
    site_id: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=MAX_PER_PAGE),
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
@limiter.limit(settings.rate_limit_default, key_func=site_token_key)
async def submit_feedback(
    session_id: str,
    data: FeedbackRequest,
    request: Request,
    repos: Repositories = Depends(get_repos),
    authorization: str | None = Header(default=None),
    site_token: str | None = None,
):
    """Widget feedback submission.

    Site token is read from the ``Authorization: Bearer <site_token>`` header
    and is now required — a request with no token is rejected before the
    session is even looked up, so an unauthenticated caller can't use this
    endpoint to probe which session ids exist. The legacy ``?site_token=...``
    query param is still accepted for one release cycle; using it logs a
    deprecation warning so we can remove it safely.
    """
    header_token = extract_bearer_token(authorization)
    resolved_token = header_token or site_token
    if not resolved_token:
        raise HTTPException(status_code=401, detail="Site token required")
    if site_token and not header_token:
        logger.warning(
            "Deprecated feedback site_token query param used",
            session_id=session_id,
        )

    session = await repos.chat_sessions.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    site = await repos.sites.get_by_token(resolved_token)
    if not site or site.get("id") != session.get("site_id"):
        raise HTTPException(status_code=403, detail="Session does not belong to this site")

    messages = session.get("messages", [])
    if data.message_index >= len(messages):
        raise HTTPException(status_code=400, detail="Invalid message index")
    messages[data.message_index]["feedback"] = data.rating
    await repos.chat_sessions.update_messages(session_id, messages)
    return {"message": "Feedback recorded"}
