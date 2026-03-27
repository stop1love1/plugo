from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from repositories import get_repos, Repositories
from providers.factory import get_all_providers

router = APIRouter(prefix="/api/sites", tags=["sites"])


class SiteCreate(BaseModel):
    name: str
    url: str
    llm_provider: str = "claude"
    llm_model: str = "claude-sonnet-4-20250514"
    primary_color: str = "#6366f1"
    greeting: str = "Xin chào! Tôi có thể giúp gì cho bạn?"
    allowed_domains: str = ""


class SiteUpdate(BaseModel):
    name: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    primary_color: Optional[str] = None
    greeting: Optional[str] = None
    position: Optional[str] = None
    allowed_domains: Optional[str] = None


@router.post("")
async def create_site(data: SiteCreate, repos: Repositories = Depends(get_repos)):
    site = await repos.sites.create(data.model_dump())
    return site


@router.get("")
async def list_sites(repos: Repositories = Depends(get_repos)):
    return await repos.sites.list_all()


@router.get("/providers/list")
async def list_providers():
    return get_all_providers()


@router.get("/{site_id}")
async def get_site(site_id: str, repos: Repositories = Depends(get_repos)):
    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


@router.put("/{site_id}")
async def update_site(site_id: str, data: SiteUpdate, repos: Repositories = Depends(get_repos)):
    site = await repos.sites.update(site_id, data.model_dump(exclude_none=True))
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


@router.delete("/{site_id}")
async def delete_site(site_id: str, repos: Repositories = Depends(get_repos)):
    ok = await repos.sites.delete(site_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Site not found")
    return {"message": "Site deleted"}
