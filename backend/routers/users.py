import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from repositories import get_repos, Repositories
from auth import get_current_user, TokenData, hash_password
from logging_config import logger

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("")
async def list_users(
    repos: Repositories = Depends(get_repos),
    user: TokenData = Depends(get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return await repos.users.list_all()


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="viewer", pattern="^(admin|viewer)$")


@router.post("")
async def create_user(
    data: CreateUserRequest,
    repos: Repositories = Depends(get_repos),
    user: TokenData = Depends(get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    existing = await repos.users.get_by_username(data.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    new_user = await repos.users.create({
        "id": str(uuid.uuid4()),
        "username": data.username,
        "password_hash": hash_password(data.password),
        "role": data.role,
    })
    try:
        await repos.audit_logs.create({
            "user_id": user.sub,
            "username": user.sub,
            "action": "create",
            "resource_type": "user",
            "resource_id": new_user["id"],
            "details": json.dumps({"username": data.username, "role": data.role}),
        })
    except Exception as e:
        logger.warning("Failed to create audit log", error=str(e))
    return {"id": new_user["id"], "username": new_user["username"], "role": new_user["role"]}


class UpdateRoleRequest(BaseModel):
    role: str = Field(pattern="^(admin|viewer)$")


@router.put("/{user_id}/role")
async def update_user_role(
    user_id: str,
    data: UpdateRoleRequest,
    repos: Repositories = Depends(get_repos),
    user: TokenData = Depends(get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    updated = await repos.users.update_role(user_id, data.role)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return updated


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    repos: Repositories = Depends(get_repos),
    user: TokenData = Depends(get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if user.sub == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    ok = await repos.users.delete(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted"}
