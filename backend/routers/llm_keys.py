"""LLM API Key management — save/retrieve provider API keys via dashboard."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy import select
from database import async_session
from models.llm_key import LLMKey
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


@router.get("")
async def list_keys(
    user: TokenData = Depends(get_current_user),
):
    """List all saved LLM keys (masked)."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    async with async_session() as db:
        result = await db.execute(select(LLMKey))
        keys = result.scalars().all()
        return [
            {
                "id": k.id,
                "provider": k.provider,
                "api_key_masked": _mask_key(_decrypt_key_safe(k.api_key)),
                "label": k.label,
                "updated_at": k.updated_at.isoformat() if k.updated_at else None,
            }
            for k in keys
        ]


def _decrypt_key_safe(encrypted_key: str) -> str:
    """Decrypt a key, falling back to raw value for legacy unencrypted data."""
    try:
        return decrypt_value(encrypted_key)
    except Exception:
        return encrypted_key


@router.post("")
async def save_key(
    data: KeySave,
    user: TokenData = Depends(get_current_user),
):
    """Save or update an API key for a provider."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    async with async_session() as db:
        result = await db.execute(select(LLMKey).where(LLMKey.provider == data.provider))
        existing = result.scalar_one_or_none()

        encrypted_key = encrypt_value(data.api_key)
        if existing:
            existing.api_key = encrypted_key
            existing.label = data.label
        else:
            db.add(LLMKey(provider=data.provider, api_key=encrypted_key, label=data.label))

        await db.commit()

    from providers.factory import refresh_key_cache
    await refresh_key_cache()

    return {"message": f"API key for {data.provider} saved", "provider": data.provider}


@router.delete("/{provider}")
async def delete_key(
    provider: str,
    user: TokenData = Depends(get_current_user),
):
    """Delete an API key."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    async with async_session() as db:
        result = await db.execute(select(LLMKey).where(LLMKey.provider == provider))
        existing = result.scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="Key not found")
        await db.delete(existing)
        await db.commit()

    return {"message": f"API key for {provider} deleted"}


async def get_key_for_provider(provider: str) -> Optional[str]:
    """Get the API key for a provider from DB. Used by provider factory."""
    try:
        async with async_session() as db:
            result = await db.execute(select(LLMKey).where(LLMKey.provider == provider))
            key = result.scalar_one_or_none()
            if not key:
                return None
            return _decrypt_key_safe(key.api_key)
    except Exception:
        return None
