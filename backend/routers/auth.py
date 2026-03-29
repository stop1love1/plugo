"""
Authentication router — env-based single admin login.

Credentials are set via USERNAME / PASSWORD in .env
"""

import json
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from repositories import get_repos, Repositories
from auth import verify_credentials, create_access_token, get_current_user, TokenData
from config import settings
from logging_config import logger

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, repos: Repositories = Depends(get_repos)):
    """Authenticate against env credentials and return a JWT token."""
    if not verify_credentials(data.username, data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(subject=settings.admin_username, role="admin")
    try:
        await repos.audit_logs.create({
            "user_id": settings.admin_username,
            "username": settings.admin_username,
            "action": "login",
            "resource_type": "auth",
            "resource_id": settings.admin_username,
            "details": json.dumps({"username": settings.admin_username}),
        })
    except Exception as e:
        logger.warning("Failed to create audit log", error=str(e))
    return TokenResponse(
        access_token=token,
        role="admin",
        username=settings.admin_username,
    )


@router.post("/refresh")
async def refresh_token(user: TokenData = Depends(get_current_user)):
    """Issue a new access token using the current valid token."""
    new_token = create_access_token(subject=user.sub, role=user.role)
    return {"access_token": new_token, "token_type": "bearer"}


@router.get("/me")
async def get_me(user: TokenData = Depends(get_current_user)):
    """Return current user info from token."""
    return {"user_id": user.sub, "role": user.role, "username": user.sub}
