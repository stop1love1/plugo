from fastapi import APIRouter, Depends
from repositories import get_repos, Repositories
from auth import get_current_user, TokenData

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
async def list_audit_logs(
    page: int = 1,
    per_page: int = 50,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    return await repos.audit_logs.list_by_site(page, per_page)
