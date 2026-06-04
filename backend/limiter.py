"""Shared slowapi rate limiter.

Lives in its own module (rather than main.py) so routers can apply the
``@limiter.limit(...)`` decorator at import time without creating a circular
import with main.py — main.py imports the routers *before* it would otherwise
have constructed the limiter.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from config import settings

# Default key: per-IP. Public embeddable endpoints (SSE, WebSocket) override
# with `site_token_key` from utils.rate_limit so one noisy embedder can't
# starve other tenants sharing its egress IP (e.g. behind a CDN).
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_default])
