import json
import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from auth import get_current_user, TokenData
from providers.factory import get_all_providers, get_embedding_providers
from logging_config import logger

router = APIRouter(prefix="/api/models", tags=["models"])

CUSTOM_MODELS_FILE = os.path.join("data", "custom_models.json")


def _load_custom_models() -> list[dict]:
    if not os.path.exists(CUSTOM_MODELS_FILE):
        return []
    try:
        with open(CUSTOM_MODELS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_custom_models(models: list[dict]):
    os.makedirs("data", exist_ok=True)
    with open(CUSTOM_MODELS_FILE, "w", encoding="utf-8") as f:
        json.dump(models, f, indent=2, ensure_ascii=False)


class CustomModelCreate(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    model_id: str = Field(min_length=1, max_length=200)
    model_name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)


class CustomModelDelete(BaseModel):
    provider: str
    model_id: str


@router.get("/providers")
async def list_all_providers(_user: TokenData = Depends(get_current_user)):
    """Get all providers with their models (built-in + custom)."""
    providers = get_all_providers()
    custom_models = _load_custom_models()

    # Merge custom models into existing providers or create new provider entries
    for cm in custom_models:
        provider_found = False
        for p in providers:
            if p["id"] == cm["provider"]:
                p["models"].append({
                    "id": cm["model_id"],
                    "name": cm["model_name"],
                    "description": cm.get("description", "Custom model"),
                    "custom": True,
                })
                provider_found = True
                break
        if not provider_found:
            providers.append({
                "id": cm["provider"],
                "name": cm["provider"].title(),
                "models": [{
                    "id": cm["model_id"],
                    "name": cm["model_name"],
                    "description": cm.get("description", "Custom model"),
                    "custom": True,
                }],
                "requires_key": True,
                "has_key": False,
                "custom": True,
            })

    return providers


@router.get("/embedding-providers")
async def list_embedding_providers(_user: TokenData = Depends(get_current_user)):
    """Get all embedding providers."""
    return get_embedding_providers()


@router.get("/custom")
async def list_custom_models(_user: TokenData = Depends(get_current_user)):
    """List all custom models."""
    return _load_custom_models()


@router.post("/custom")
async def add_custom_model(
    data: CustomModelCreate,
    _user: TokenData = Depends(get_current_user),
):
    """Add a custom model to a provider."""
    models = _load_custom_models()

    # Check for duplicates
    for m in models:
        if m["provider"] == data.provider and m["model_id"] == data.model_id:
            raise HTTPException(status_code=409, detail="Model already exists for this provider")

    models.append({
        "provider": data.provider,
        "model_id": data.model_id,
        "model_name": data.model_name,
        "description": data.description,
    })
    _save_custom_models(models)
    logger.info("Custom model added", provider=data.provider, model_id=data.model_id)
    return {"message": "Model added", "provider": data.provider, "model_id": data.model_id}


@router.delete("/custom")
async def delete_custom_model(
    data: CustomModelDelete,
    _user: TokenData = Depends(get_current_user),
):
    """Remove a custom model."""
    models = _load_custom_models()
    original_len = len(models)
    models = [m for m in models if not (m["provider"] == data.provider and m["model_id"] == data.model_id)]

    if len(models) == original_len:
        raise HTTPException(status_code=404, detail="Custom model not found")

    _save_custom_models(models)
    logger.info("Custom model deleted", provider=data.provider, model_id=data.model_id)
    return {"message": "Model removed"}
