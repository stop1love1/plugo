import json

from auth import TokenData, get_current_user
from fastapi import APIRouter, Depends, HTTPException
from logging_config import logger
from pydantic import BaseModel
from utils.crypto import decrypt_value, encrypt_value

from agent.tools import tool_executor
from knowledge.crawler import _is_safe_public_url
from repositories import Repositories, get_repos

router = APIRouter(prefix="/api/tools", tags=["tools"])


class ToolCreate(BaseModel):
    site_id: str
    name: str
    description: str
    method: str = "GET"
    url: str
    params_schema: dict = {}
    headers: dict = {}
    auth_type: str | None = None
    auth_value: str | None = None


class ToolUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    method: str | None = None
    url: str | None = None
    params_schema: dict | None = None
    headers: dict | None = None
    auth_type: str | None = None
    auth_value: str | None = None
    enabled: bool | None = None


class ToolTestRequest(BaseModel):
    params: dict = {}


async def validate_tool_url(url: str) -> tuple[bool, str]:
    """Prevent SSRF by blocking internal/private IPs and cloud metadata endpoints.

    Uses the shared SSRF helper (with DNS resolution) to match the guard applied
    at tool execution time. Tools never get the allow_private escape hatch.
    """
    return await _is_safe_public_url(url, allow_private=False)


@router.get("")
async def list_tools(site_id: str, repos: Repositories = Depends(get_repos), _user: TokenData = Depends(get_current_user)):
    tools = await repos.tools.list_by_site(site_id)
    for tool in tools:
        if tool.get("auth_value"):
            try:
                tool["auth_value"] = decrypt_value(tool["auth_value"])
            except ValueError as e:
                # Dashboard listing — surface "" rather than unreadable ciphertext.
                logger.warning(
                    "Tool auth_value decryption failed in list_tools",
                    tool_id=tool.get("id"),
                    error=str(e),
                )
                tool["auth_value"] = ""
    return tools


@router.post("")
async def create_tool(data: ToolCreate, repos: Repositories = Depends(get_repos), user: TokenData = Depends(get_current_user)):
    safe, reason = await validate_tool_url(data.url)
    if not safe:
        raise HTTPException(status_code=400, detail=f"URL rejected: {reason}")
    tool_data = data.model_dump()
    if tool_data.get("auth_value"):
        tool_data["auth_value"] = encrypt_value(tool_data["auth_value"])
    tool = await repos.tools.create(tool_data)
    try:
        await repos.audit_logs.create({
            "user_id": user.sub,
            "username": user.sub,
            "action": "create",
            "resource_type": "tool",
            "resource_id": tool["id"],
            "details": json.dumps({"name": data.name, "site_id": data.site_id}),
        })
    except Exception as e:
        logger.warning("Failed to create audit log", error=str(e))
    return {"id": tool["id"], "message": "Tool created"}


@router.put("/{tool_id}")
async def update_tool(tool_id: str, data: ToolUpdate, repos: Repositories = Depends(get_repos), user: TokenData = Depends(get_current_user)):
    if data.url is not None:
        safe, reason = await validate_tool_url(data.url)
        if not safe:
            raise HTTPException(status_code=400, detail=f"URL rejected: {reason}")
    update_data = data.model_dump(exclude_none=True)
    if update_data.get("auth_value"):
        update_data["auth_value"] = encrypt_value(update_data["auth_value"])
    tool = await repos.tools.update(tool_id, update_data)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    try:
        # Exclude sensitive fields from audit details
        audit_data = data.model_dump(exclude_none=True)
        audit_data.pop("auth_value", None)
        await repos.audit_logs.create({
            "user_id": user.sub,
            "username": user.sub,
            "action": "update",
            "resource_type": "tool",
            "resource_id": tool_id,
            "details": json.dumps(audit_data),
        })
    except Exception as e:
        logger.warning("Failed to create audit log", error=str(e))
    return {"message": "Tool updated"}


@router.delete("/{tool_id}")
async def delete_tool(tool_id: str, repos: Repositories = Depends(get_repos), user: TokenData = Depends(get_current_user)):
    ok = await repos.tools.delete(tool_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Tool not found")
    try:
        await repos.audit_logs.create({
            "user_id": user.sub,
            "username": user.sub,
            "action": "delete",
            "resource_type": "tool",
            "resource_id": tool_id,
            "details": json.dumps({"tool_id": tool_id}),
        })
    except Exception as e:
        logger.warning("Failed to create audit log", error=str(e))
    return {"message": "Tool deleted"}


@router.post("/{tool_id}/test")
async def test_tool(tool_id: str, data: ToolTestRequest, repos: Repositories = Depends(get_repos), _user: TokenData = Depends(get_current_user)):
    tool = await repos.tools.get_by_id(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    # Re-validate URL at execution time to prevent DNS rebinding attacks.
    # Note: the executor also re-runs this check; we raise here for a clear 400.
    safe, reason = await validate_tool_url(tool["url"])
    if not safe:
        raise HTTPException(status_code=400, detail=f"URL rejected: {reason}")

    # Decrypt auth_value before executing
    auth_value = tool.get("auth_value")
    if auth_value:
        try:
            auth_value = decrypt_value(auth_value)
        except ValueError as e:
            logger.warning(
                "Tool auth_value decryption failed during test", tool_id=tool_id, error=str(e)
            )
            raise HTTPException(
                status_code=500,
                detail="Tool credential cannot be decrypted — re-enter the auth value.",
            ) from e

    result = await tool_executor.execute_tool(
        tool_meta={
            "method": tool["method"],
            "url": tool["url"],
            "auth_type": tool.get("auth_type"),
            "auth_value": auth_value,
            "headers": tool.get("headers", {}),
        },
        arguments=data.params,
    )
    return result
