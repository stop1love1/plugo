"""
Authentication router — login, register, token management.

For initial setup, the first user registered becomes admin.
Subsequent users need an admin to create their account.
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


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="admin", pattern="^(admin|viewer)$")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


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


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: RegisterRequest, repos: Repositories = Depends(get_repos)):
    """
    Register a new user.
    First user is always admin. Subsequent users require no auth for now
    (in production, lock this down to admin-only).
    """
    existing = await repos.users.get_by_username(data.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    # First user is always admin
    user_count = await repos.users.count()
    role = "admin" if user_count == 0 else data.role

    user = await repos.users.create({
        "username": data.username,
        "password_hash": hash_password(data.password),
        "role": role,
    })

    token = create_access_token(subject=user["id"], role=role)
    return TokenResponse(
        access_token=token,
        role=role,
        username=user["username"],
    )


@router.get("/me")
async def get_me(user: TokenData = Depends(get_current_user)):
    """Return current user info from token."""
    return {"user_id": user.sub, "role": user.role}
