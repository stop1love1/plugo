from fastapi import APIRouter, Depends
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
