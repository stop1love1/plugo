import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import TokenData, get_current_user
from logging_config import logger
from providers.factory import get_all_providers, get_llm_provider
from repositories import Repositories, get_repos
from routers.chat import invalidate_site_cache

router = APIRouter(prefix="/api/sites", tags=["sites"])


class SiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2048)
    llm_provider: str = Field(default="claude", pattern="^(claude|openai|gemini|ollama|lmstudio)$")
    llm_model: str = "claude-sonnet-4-20250514"
    primary_color: str = Field(default="#6366f1", pattern="^#[0-9a-fA-F]{6}$")
    greeting: str = "Hello! How can I help you?"
    position: str = Field(default="bottom-right", pattern="^(bottom-right|bottom-left)$")
    widget_title: str = ""
    dark_mode: str = Field(default="auto", pattern="^(auto|light|dark)$")
    show_branding: bool = True
    allowed_domains: str = ""


class SiteUpdate(BaseModel):
    """Editable site settings from the dashboard."""
    name: str | None = None
    url: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    primary_color: str | None = None
    greeting: str | None = None
    position: str | None = None
    widget_title: str | None = None
    dark_mode: str | None = None
    show_branding: bool | None = None
    allowed_domains: str | None = None
    suggestions: list[str] | None = None
    system_prompt: str | None = None
    bot_rules: str | None = None
    response_language: str | None = None  # "auto" | "vi" | "en"


class ApprovalUpdate(BaseModel):
    is_approved: bool


async def verify_site_model_config(provider: str, model: str) -> None:
    """Fail fast when a configured site model cannot answer a minimal prompt."""
    supported_providers = {item["id"] for item in get_all_providers()}
    if provider not in supported_providers:
        raise HTTPException(status_code=400, detail=f"Provider '{provider}' is not supported.")

    try:
        llm_provider = get_llm_provider(provider, model)
        result = await asyncio.wait_for(
            llm_provider.chat(
                [{"role": "user", "content": "Reply with OK only."}],
                temperature=0,
            ),
            timeout=20,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{model}' for provider '{provider}' failed verification: {exc}",
        ) from exc

    if not isinstance(result, dict) or not result.get("content"):
        raise HTTPException(
            status_code=400,
            detail=f"Model '{model}' for provider '{provider}' returned an empty response during verification.",
        )


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
    existing_site = await repos.sites.get_by_id(site_id)
    if not existing_site:
        raise HTTPException(status_code=404, detail="Site not found")

    update_payload = data.model_dump(exclude_none=True)
    if "llm_provider" in update_payload or "llm_model" in update_payload:
        provider = update_payload.get("llm_provider", existing_site["llm_provider"])
        model = update_payload.get("llm_model", existing_site["llm_model"])
        await verify_site_model_config(provider, model)

    site = await repos.sites.update(site_id, update_payload)
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
