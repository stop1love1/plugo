import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from repositories import get_repos, Repositories
from providers.factory import get_all_providers
from auth import get_current_user, TokenData
from routers.chat import invalidate_site_cache
from logging_config import logger

router = APIRouter(prefix="/api/sites", tags=["sites"])


class SiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2048)
    llm_provider: str = Field(default="claude", pattern="^(claude|openai|gemini|ollama|lmstudio)$")
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
    suggestions: Optional[list[str]] = None


class ApprovalUpdate(BaseModel):
    is_approved: bool


@router.post("")
async def create_site(
    data: SiteCreate,
    repos: Repositories = Depends(get_repos),
    user: TokenData = Depends(get_current_user),
):
    site = await repos.sites.create(data.model_dump())
    try:
        await repos.audit_logs.create({
            "user_id": user.sub,
            "username": user.sub,
            "action": "create",
            "resource_type": "site",
            "resource_id": site["id"],
            "details": json.dumps({"name": data.name, "url": data.url}),
        })
    except Exception as e:
        logger.warning("Failed to create audit log", error=str(e))
    return site


@router.get("")
async def list_sites(
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    return await repos.sites.list_all()


@router.get("/providers/list")
async def list_providers(_user: TokenData = Depends(get_current_user)):
    return get_all_providers()


# --- Approval (must be before /{site_id} to avoid route conflict) ---

@router.put("/{site_id}/approval")
async def update_site_approval(
    site_id: str,
    data: ApprovalUpdate,
    repos: Repositories = Depends(get_repos),
    user: TokenData = Depends(get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    site = await repos.sites.update(site_id, {"is_approved": data.is_approved})
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return {"message": "Approval updated", "is_approved": site["is_approved"]}


# --- CRUD (generic /{site_id} routes last) ---

@router.get("/{site_id}")
async def get_site(site_id: str, repos: Repositories = Depends(get_repos), _user: TokenData = Depends(get_current_user)):
    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


@router.put("/{site_id}")
async def update_site(
    site_id: str,
    data: SiteUpdate,
    repos: Repositories = Depends(get_repos),
    user: TokenData = Depends(get_current_user),
):
    site = await repos.sites.update(site_id, data.model_dump(exclude_none=True))
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    invalidate_site_cache()  # Clear all since we don't know token from site_id easily
    try:
        await repos.audit_logs.create({
            "user_id": user.sub,
            "username": user.sub,
            "action": "update",
            "resource_type": "site",
            "resource_id": site_id,
            "details": json.dumps(data.model_dump(exclude_none=True)),
        })
    except Exception as e:
        logger.warning("Failed to create audit log", error=str(e))
    return site


@router.delete("/{site_id}")
async def delete_site(
    site_id: str,
    repos: Repositories = Depends(get_repos),
    user: TokenData = Depends(get_current_user),
):
    ok = await repos.sites.delete(site_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Site not found")
    invalidate_site_cache()  # Clear all since we don't know token from site_id easily
    try:
        await repos.audit_logs.create({
            "user_id": user.sub,
            "username": user.sub,
            "action": "delete",
            "resource_type": "site",
            "resource_id": site_id,
            "details": json.dumps({"site_id": site_id}),
        })
    except Exception as e:
        logger.warning("Failed to create audit log", error=str(e))
    return {"message": "Site deleted"}
