from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from repositories import get_repos, Repositories
from agent.tools import tool_executor

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


@router.get("")
async def list_tools(site_id: str, repos: Repositories = Depends(get_repos)):
    return await repos.tools.list_by_site(site_id)


@router.post("")
async def create_tool(data: ToolCreate, repos: Repositories = Depends(get_repos)):
    tool = await repos.tools.create(data.model_dump())
    return {"id": tool["id"], "message": "Tool created"}


@router.put("/{tool_id}")
async def update_tool(tool_id: str, data: ToolUpdate, repos: Repositories = Depends(get_repos)):
    tool = await repos.tools.update(tool_id, data.model_dump(exclude_none=True))
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"message": "Tool updated"}


@router.delete("/{tool_id}")
async def delete_tool(tool_id: str, repos: Repositories = Depends(get_repos)):
    ok = await repos.tools.delete(tool_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"message": "Tool deleted"}


@router.post("/{tool_id}/test")
async def test_tool(tool_id: str, data: ToolTestRequest, repos: Repositories = Depends(get_repos)):
    tool = await repos.tools.get_by_id(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    result = await tool_executor.execute_tool(
        tool_meta={
            "method": tool["method"],
            "url": tool["url"],
            "auth_type": tool.get("auth_type"),
            "auth_value": tool.get("auth_value"),
            "headers": tool.get("headers", {}),
        },
        arguments=data.params,
    )
    return result
