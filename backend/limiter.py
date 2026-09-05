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
#
# `default_limits` below is inert as this app is wired. slowapi consults it only
# from `SlowAPIMiddleware`, which main.py does not install, so a route without an
# explicit `@limiter.limit(...)` is never rate limited at all — 200 consecutive
# requests to `/health` under an enabled limiter all return 200. Read that before
# reasoning about the blast radius of anything here: only decorated routes are
# affected by this construction. Adding `SlowAPIMiddleware` would switch this
# limit on for *every* route at once, putting bursty admin traffic (a Flows page
# fetching one screenshot per step, any per-item dashboard GET) under a single
# 60/minute per-IP bucket — give those routes explicit limits first.
#
# key_style="endpoint" (slowapi's default is "url") scopes each bucket to the
# endpoint function rather than the request path. It has to be: both public
# routes carry a caller-supplied value *in the path* — the site_token in
# `/api/chat/{site_token}/stream`, the session_id in
# `/api/sessions/{session_id}/feedback` — so under url-scoping a caller varying
# either one mints a fresh bucket per request and no limit on those routes can
# ever bind, whatever it is keyed by. Because it only reaches decorated routes,
# it rescopes exactly three: the two public ones (the point of the change) and
# `/api/auth/login`, whose path is fixed, so that one is a bucket rename with no
# behaviour change.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default],
    key_style="endpoint",
)
