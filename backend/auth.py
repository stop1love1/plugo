"""
Authentication & authorization for Plugo API.

Two auth mechanisms:
1. JWT tokens — for dashboard users (admin/site owners)
2. API keys — for programmatic access

Public endpoints (no auth required):
- GET /health, GET /
- WS /ws/chat/{site_token} (uses site token, not user auth)
- GET /static/* (widget JS)
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from config import settings

# --- Password hashing ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- JWT config ---
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# --- Bearer token scheme ---
bearer_scheme = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    sub: str  # username or user_id
    role: str = "admin"  # admin | viewer
    exp: Optional[datetime] = None


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, role: str = "admin", expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return TokenData(**payload)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def generate_api_key() -> str:
    """Generate a secure API key for programmatic access."""
    return f"plugo_{secrets.token_urlsafe(32)}"


# --- FastAPI Dependencies ---

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> TokenData:
    """
    Dependency: requires a valid JWT token.
    Use on all dashboard/admin endpoints.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(credentials.credentials)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[TokenData]:
    """Dependency: returns user if token provided, None otherwise."""
    if credentials is None:
        return None
    try:
        return decode_access_token(credentials.credentials)
    except HTTPException:
        return None
