"""Shared slowapi rate limiter.

Lives in its own module (rather than main.py) so routers can apply the
``@limiter.limit(...)`` decorator at import time without creating a circular
import with main.py — main.py imports the routers *before* it would otherwise
have constructed the limiter.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# There is no global rate limit. Exactly three routes carry one, each via an
# explicit `@limiter.limit(...)`:
#
#   POST /api/auth/login                 per IP      (rate_limit_auth)
#   POST /api/chat/{site_token}/stream   per token + per IP  (chat, public_ip)
#   POST /api/sessions/{id}/feedback     per token + per IP  (default, public_ip)
#
# Everything else is unlimited and relies on authentication. slowapi reaches a
# route only through that decorator or through `SlowAPIMiddleware`, and main.py
# installs no such middleware — so an undecorated route never consults the
# limiter at all. This module deliberately passes no `default_limits`: it would
# be read as an app-wide floor while providing none, since slowapi consults
# `default_limits` only from that same middleware. (The `rate_limit.default`
# *config key* is still live — `routers/sessions.py` uses it as the feedback
# endpoint's token-keyed limit.)
#
# The two public endpoints carry two stacked limits each — per site_token for
# tenant fairness, per client IP as the ceiling a token-rotating caller can't
# lift. See `utils/rate_limit.py` for why one key cannot do both.
#
# key_style="endpoint" (slowapi's default is "url") scopes each bucket to the
# endpoint function rather than the request path. It has to be: both public
# routes carry a caller-supplied value *in the path* — the site_token in
# `/api/chat/{site_token}/stream`, the session_id in
# `/api/sessions/{session_id}/feedback` — so under url-scoping a caller varying
# either one mints a fresh bucket per request and no limit on those routes can
# ever bind, whatever it is keyed by. It reaches only the three routes above;
# for `/api/auth/login`, whose path is fixed, it is a bucket rename with no
# behaviour change.
#
# Installing `SlowAPIMiddleware` later would change all of that at once: every
# route would fall under whatever defaults are configured, endpoint-scoped, so
# bursty admin traffic (a Flows page fetching one screenshot per step, any
# per-item dashboard GET) would share a single per-IP bucket and 429 the admin
# on their own dashboard. Give those routes explicit limits that fit their call
# pattern first — `tests/test_rate_limit_public.py::
# test_bursty_dashboard_route_is_not_rate_limited` is the guard that catches it.
limiter = Limiter(key_func=get_remote_address, key_style="endpoint")
