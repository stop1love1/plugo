"""Rate-limit key functions and per-site-token bucket for public endpoints.

Public (embeddable) endpoints bucket by `site_token` so a single noisy embedder
behind a CDN doesn't starve other tenants that share its egress IP.
Admin endpoints remain IP-keyed — they're authenticated, so IPs are meaningful.
"""

import asyncio
from collections import defaultdict
from time import time

from fastapi import Request
from slowapi.util import get_remote_address


def site_token_key(request: Request) -> str:
    """slowapi key_func: bucket per site_token (falls back to client IP).

    The public routes that use this expose `site_token` as a path parameter
    (`/api/chat/{site_token}/stream`). When absent, we degrade to IP so the
    default rate-limit contract still holds.
    """
    token = None
    try:
        token = request.path_params.get("site_token")
    except Exception:
        token = None
    if token:
        return f"site:{token}"
    return get_remote_address(request)


class SiteTokenWSRateLimiter:
    """Sliding-window rate limiter keyed by (site_token, session_id).

    Used for WebSocket messages, which slowapi doesn't cover. Keeping one
    bucket per (token, session) means per-tenant isolation AND per-visitor
    fairness within a tenant. Sessions without a token fall back to session-only
    keying, matching legacy behaviour.
    """

    # Sweep-interval: the global stale-bucket purge is O(N) over the whole dict,
    # so run it only once every SWEEP_EVERY allowed-calls. Correctness of the
    # caller's own bucket is unaffected — the per-key filter below already
    # expires stale timestamps on every call.
    SWEEP_EVERY = 100

    def __init__(self, window_seconds: int = 60, max_requests: int = 20):
        self.window = window_seconds
        self.max = max_requests
        self._timestamps: dict[str, list[float]] = {}
        self._calls_since_sweep: int = 0

    @staticmethod
    def _key(session_id: str, site_token: str | None) -> str:
        return f"{site_token}:{session_id}" if site_token else session_id

    def is_allowed(self, session_id: str, site_token: str | None = None) -> bool:
        now = time()
        key = self._key(session_id, site_token)

        # Amortised global sweep: only run every SWEEP_EVERY calls so we aren't
        # O(N) per message at scale. Per-bucket expiry below handles correctness
        # for the caller's own session.
        self._calls_since_sweep += 1
        if self._calls_since_sweep >= self.SWEEP_EVERY:
            self._calls_since_sweep = 0
            stale_keys = [
                k for k, ts in self._timestamps.items()
                if k != key and all(now - t >= self.window for t in ts)
            ]
            for k in stale_keys:
                del self._timestamps[k]

        timestamps = [t for t in self._timestamps.get(key, []) if now - t < self.window]
        if len(timestamps) >= self.max:
            self._timestamps[key] = timestamps
            return False
        timestamps.append(now)
        self._timestamps[key] = timestamps
        return True

    def cleanup(self, session_id: str, site_token: str | None = None) -> None:
        self._timestamps.pop(self._key(session_id, site_token), None)


class SSEConcurrencyGuard:
    """Cap simultaneous open SSE streams per site_token.

    slowapi gates requests-per-window but not concurrent long-lived streams;
    without this cap an attacker can open thousands of SSE connections on the
    same site_token and pin server memory / file descriptors indefinitely.
    """

    def __init__(self, max_per_token: int = 10):
        self.max_per_token = max_per_token
        self._active: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def acquire(self, site_token: str) -> bool:
        """Reserve a slot for this token. Returns False if the cap is reached."""
        async with self._lock:
            if self._active[site_token] >= self.max_per_token:
                return False
            self._active[site_token] += 1
            return True

    async def release(self, site_token: str) -> None:
        """Release a previously acquired slot. Safe to call multiple times."""
        async with self._lock:
            count = self._active.get(site_token, 0)
            if count <= 1:
                self._active.pop(site_token, None)
            else:
                self._active[site_token] = count - 1

    def active_count(self, site_token: str) -> int:
        """Current active streams for a token — for tests / introspection."""
        return self._active.get(site_token, 0)


# Process-wide SSE concurrency guard. Size comes from settings at import time;
# if settings are unavailable (e.g. unusual import order in tests), fall back
# to the documented default of 10.
def _default_sse_cap() -> int:
    try:
        from config import settings
        return int(getattr(settings, "rate_limit_sse_concurrent", 10))
    except Exception:
        return 10


_sse_guard = SSEConcurrencyGuard(max_per_token=_default_sse_cap())


async def acquire_sse_slot(site_token: str) -> bool:
    """Acquire a concurrent-SSE slot for this site_token. False if at cap."""
    return await _sse_guard.acquire(site_token)


async def release_sse_slot(site_token: str) -> None:
    """Release a previously acquired SSE slot. Safe to call unconditionally."""
    await _sse_guard.release(site_token)


def sse_active_count(site_token: str) -> int:
    """Return number of active SSE streams for a token (tests/introspection)."""
    return _sse_guard.active_count(site_token)


def _reset_sse_guard_for_tests(max_per_token: int | None = None) -> None:
    """Test helper: reset the guard with an optional new cap.

    Lives in the utils module so tests don't reach into private state directly.
    """
    global _sse_guard
    cap = max_per_token if max_per_token is not None else _default_sse_cap()
    _sse_guard = SSEConcurrencyGuard(max_per_token=cap)
