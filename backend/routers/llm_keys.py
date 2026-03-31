"""LLM API Key management — save/retrieve provider API keys via dashboard."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from repositories import get_repos, Repositories
from auth import get_current_user, TokenData
from utils.crypto import encrypt_value, decrypt_value

router = APIRouter(prefix="/api/llm-keys", tags=["llm-keys"])


class KeySave(BaseModel):
    provider: str = Field(pattern="^(claude|openai|gemini|lmstudio)$")
    api_key: str = Field(min_length=1, max_length=500)
    label: str = ""


class KeyUpdate(BaseModel):
    api_key: Optional[str] = Field(None, min_length=1, max_length=500)
    label: Optional[str] = None


def _mask_key(key: str) -> str:
    """Show only last 4 chars for security."""
    if len(key) <= 4:
        return "****"
    return "****" + key[-4:]


def _decrypt_key_safe(encrypted_key: str) -> str:
    """Decrypt a key, falling back to raw value for legacy unencrypted data."""
    try:
        return decrypt_value(encrypted_key)
    except Exception:
        return encrypted_key


@router.get("")
async def list_keys(
    user: TokenData = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
):
    """List all saved LLM keys (masked)."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    keys = await repos.llm_keys.list_all()
    return [
        {
            "id": k["id"],
            "provider": k["provider"],
            "api_key_masked": _mask_key(_decrypt_key_safe(k["api_key"])),
            "label": k.get("label", ""),
            "updated_at": k.get("updated_at"),
        }
        for k in keys
    ]


@router.post("")
async def save_key(
    data: KeySave,
    user: TokenData = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
):
    """Save or update an API key for a provider."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    encrypted_key = encrypt_value(data.api_key)
    await repos.llm_keys.upsert(data.provider, {"api_key": encrypted_key, "label": data.label})

    from providers.factory import refresh_key_cache
    await refresh_key_cache()

    return {"message": f"API key for {data.provider} saved", "provider": data.provider}


@router.delete("/{provider}")
async def delete_key(
    provider: str,
    user: TokenData = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
):
    """Delete an API key."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    deleted = await repos.llm_keys.delete_by_provider(provider)
    if not deleted:
        raise HTTPException(status_code=404, detail="Key not found")

    from providers.factory import clear_provider_key
    clear_provider_key(provider)

    return {"message": f"API key for {provider} deleted"}


async def get_key_for_provider(provider: str) -> Optional[str]:
    """Get the API key for a provider from DB. Used by provider factory."""
    from repositories import create_repos
    try:
        repos = await create_repos()
        try:
            key = await repos.llm_keys.get_by_provider(provider)
            if not key:
                return None
            return _decrypt_key_safe(key["api_key"])
        finally:
            await repos.close()
    except Exception:
        return None
