"""
Authentication router — login, token management.

Admin accounts are created via CLI: python manage.py create-admin
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from repositories import get_repos, Repositories
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, TokenData,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


@router.get("/setup-status")
async def setup_status(repos: Repositories = Depends(get_repos)):
    """Check if any users exist (public endpoint for login page)."""
    count = await repos.users.count()
    return {"has_users": count > 0}


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, repos: Repositories = Depends(get_repos)):
    """Authenticate and return a JWT token."""
    user = await repos.users.get_by_username(data.username)
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(subject=user["id"], role=user["role"])
    return TokenResponse(
        access_token=token,
        role=user["role"],
        username=user["username"],
    )


@router.get("/me")
async def get_me(user: TokenData = Depends(get_current_user)):
    """Return current user info from token."""
    return {"user_id": user.sub, "role": user.role}
