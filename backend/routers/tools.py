import json
from urllib.parse import urlparse
import ipaddress
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from repositories import get_repos, Repositories
from agent.tools import tool_executor
from auth import get_current_user, TokenData
from logging_config import logger
from utils.crypto import encrypt_value, decrypt_value

router = APIRouter(prefix="/api/tools", tags=["tools"])


class ToolCreate(BaseModel):
    site_id: str
    name: str
    description: str
    method: str = "GET"
    url: str
    params_schema: dict = {}
    headers: dict = {}
    auth_type: Optional[str] = None
    auth_value: Optional[str] = None


class ToolUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    method: Optional[str] = None
    url: Optional[str] = None
    params_schema: Optional[dict] = None
    headers: Optional[dict] = None
    auth_type: Optional[str] = None
    auth_value: Optional[str] = None
    enabled: Optional[bool] = None


class ToolTestRequest(BaseModel):
    params: dict = {}


def validate_tool_url(url: str) -> bool:
    """Prevent SSRF by blocking internal/private IPs."""
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return False
    # Block private/internal hostnames
    blocked_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    if hostname in blocked_hosts:
        return False
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    except ValueError:
        pass  # hostname is a domain, not an IP — OK
    return True


@router.get("")
async def list_tools(site_id: str, repos: Repositories = Depends(get_repos), _user: TokenData = Depends(get_current_user)):
    tools = await repos.tools.list_by_site(site_id)
    for tool in tools:
        if tool.get("auth_value"):
            try:
                tool["auth_value"] = decrypt_value(tool["auth_value"])
            except Exception:
                pass  # Value may not be encrypted (legacy data)
    return tools


@router.post("")
async def create_tool(data: ToolCreate, repos: Repositories = Depends(get_repos), user: TokenData = Depends(get_current_user)):
    if not validate_tool_url(data.url):
        raise HTTPException(status_code=400, detail="URL targets internal network")
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
    if data.url is not None and not validate_tool_url(data.url):
        raise HTTPException(status_code=400, detail="URL targets internal network")
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
    # Note: for production, consider using an HTTP proxy that blocks internal IPs
    # at the network level, since DNS can resolve differently between checks.
    if not validate_tool_url(tool["url"]):
        raise HTTPException(status_code=400, detail="URL targets internal network")

    # Decrypt auth_value before executing
    auth_value = tool.get("auth_value")
    if auth_value:
        try:
            auth_value = decrypt_value(auth_value)
        except Exception:
            pass  # Value may not be encrypted (legacy data)

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
