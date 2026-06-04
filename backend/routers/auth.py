"""
Authentication router — env-based single admin login.

Credentials are set via USERNAME / PASSWORD in .env
"""

import json
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    CSRF_COOKIE,
    SESSION_COOKIE,
    TokenData,
    create_access_token,
    get_current_user,
    verify_credentials,
)
from config import settings
from limiter import limiter
from logging_config import logger
from repositories import Repositories, get_repos

router = APIRouter(prefix="/api/auth", tags=["auth"])

_COOKIE_MAX_AGE = ACCESS_TOKEN_EXPIRE_MINUTES * 60


def _cookie_secure() -> bool:
    """Secure cookies in production only — over plain http (dev/tests) a Secure
    cookie would never be sent back, breaking local login."""
    return os.environ.get("ENV", "development") == "production"


def _set_auth_cookies(response: Response, token: str) -> str:
    """Set the httpOnly session cookie and a readable CSRF token cookie.

    Returns the CSRF token so the login response body can echo it for clients
    that prefer to read it from the body rather than the cookie.
    """
    secure = _cookie_secure()
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=_COOKIE_MAX_AGE,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )
    return csrf_token


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    csrf_token: str | None = None


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_auth)
async def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    repos: Repositories = Depends(get_repos),
):
    """Authenticate against env credentials and return a JWT token.

    Sets the token in an httpOnly cookie (preferred for the dashboard, keeps the
    JWT out of JS-readable storage) and also returns it in the body for header-
    based API clients. Rate-limited per-IP (rate_limit_auth) to blunt brute-force
    attempts. slowapi requires the ``request`` parameter to derive the client key.
    """
    if not verify_credentials(data.username, data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(subject=settings.admin_username, role="admin")
    csrf_token = _set_auth_cookies(response, token)
    try:
        await repos.audit_logs.create(
            {
                "user_id": settings.admin_username,
                "username": settings.admin_username,
                "action": "login",
                "resource_type": "auth",
                "resource_id": settings.admin_username,
                "details": json.dumps({"username": settings.admin_username}),
            }
        )
    except Exception as e:
        logger.warning("Failed to create audit log", error=str(e))
    return TokenResponse(
        access_token=token,
        role="admin",
        username=settings.admin_username,
        csrf_token=csrf_token,
    )


@router.post("/refresh")
async def refresh_token(response: Response, user: TokenData = Depends(get_current_user)):
    """Issue a new access token using the current valid token and refresh cookies."""
    new_token = create_access_token(subject=user.sub, role=user.role)
    csrf_token = _set_auth_cookies(response, new_token)
    return {"access_token": new_token, "token_type": "bearer", "csrf_token": csrf_token}


@router.post("/logout")
async def logout(response: Response):
    """Clear the session and CSRF cookies."""
    _clear_auth_cookies(response)
    return {"message": "Logged out"}


@router.get("/me")
async def get_me(user: TokenData = Depends(get_current_user)):
    """Return current user info from token."""
    return {"user_id": user.sub, "role": user.role, "username": user.sub}
