from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from repositories import get_repos, Repositories
from providers.factory import get_all_providers
from auth import get_current_user, TokenData

router = APIRouter(prefix="/api/sites", tags=["sites"])


class SiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2048)
    llm_provider: str = Field(default="claude", pattern="^(claude|openai|gemini|ollama)$")
    llm_model: str = "claude-sonnet-4-20250514"
    primary_color: str = Field(default="#6366f1", pattern="^#[0-9a-fA-F]{6}$")
    greeting: str = "Hello! How can I help you?"
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
async def create_site(
    data: SiteCreate,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    site = await repos.sites.create(data.model_dump())
    return site


@router.get("")
async def list_sites(
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
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
async def update_site(
    site_id: str,
    data: SiteUpdate,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    site = await repos.sites.update(site_id, data.model_dump(exclude_none=True))
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


@router.delete("/{site_id}")
async def delete_site(
    site_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    ok = await repos.sites.delete(site_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Site not found")
    return {"message": "Site deleted"}
