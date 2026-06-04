from fastapi import APIRouter, Depends, Query

from auth import TokenData, get_current_user
from repositories import Repositories, get_repos

router = APIRouter(prefix="/api/audit", tags=["audit"])

# Upper bound on page size so a client can't request an unbounded result set.
MAX_PER_PAGE = 100


@router.get("")
async def list_audit_logs(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=MAX_PER_PAGE),
    action: str | None = Query(default=None, max_length=50),
    resource_type: str | None = Query(default=None, max_length=50),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    return await repos.audit_logs.list_by_site(page, per_page, action=action, resource_type=resource_type)
