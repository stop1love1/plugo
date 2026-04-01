"""
Authentication & authorization for Plugo API.

Single admin user with credentials from .env (USERNAME / PASSWORD).
JWT tokens for dashboard session management.

Public endpoints (no auth required):
- GET /health, GET /
- WS /ws/chat/{site_token} (uses site token, not user auth)
- GET /static/* (widget JS)
"""

from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from config import settings

# --- JWT config ---
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# --- Bearer token scheme ---
bearer_scheme = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    sub: str  # username
    role: str = "admin"
    exp: datetime | None = None


def verify_credentials(username: str, password: str) -> bool:
    """Verify credentials against config."""
    return username == settings.admin_username and password == settings.admin_password


def create_access_token(subject: str, role: str = "admin", expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
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
        ) from None


# --- FastAPI Dependencies ---

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> TokenData:
    """Dependency: requires a valid JWT token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(credentials.credentials)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> TokenData | None:
    """Dependency: returns user if token provided, None otherwise."""
    if credentials is None:
        return None
    try:
        return decode_access_token(credentials.credentials)
    except HTTPException:
        return None
