"""Rate-limit key functions and per-site-token bucket for public endpoints.

Public (embeddable) endpoints bucket by `site_token` so a single noisy embedder
behind a CDN doesn't starve other tenants that share its egress IP.
Admin endpoints remain IP-keyed — they're authenticated, so IPs are meaningful.

Public endpoints carry **two** stacked limits, because no single key can hold
both properties at once:

* `site_token_key` — tenant fairness. The token is the only thing that
  identifies a tenant, but it is supplied by the caller, so a caller that varies
  it gets a fresh bucket every request and the limit never binds.
* `client_ip_key` — abuse resistance. The peer address is not caller-supplied,
  so it is the one identifier a token-rotating caller cannot shed. On its own it
  would re-create the starvation problem above (tenants sharing an egress IP),
  which is why it stacks on top of the per-token limit rather than replacing it.

slowapi evaluates every limit registered against a route, so a request must
satisfy both (verified against slowapi 0.1.9 in
`tests/test_rate_limit_public.py`). Neither binds at all unless the limiter is
built with `key_style="endpoint"` — see the comment in `limiter.py`.

The WebSocket transport carries the same pair, hand-rolled because slowapi does
not reach WebSocket frames: `SiteTokenWSRateLimiter` (tenant fairness, per
`(site_token, session_id)`) and `ClientIPWSRateLimiter` (the abuse ceiling, per
peer address). Same reasoning, same split of responsibilities — see
`tests/test_ws_rate_limit_ceiling.py`.
"""

import asyncio
from collections import defaultdict
from time import time

from fastapi import Request, WebSocket
from limits import parse
from slowapi.util import get_remote_address


def extract_bearer_token(authorization: str | None) -> str | None:
    """Return the token from an `Authorization: Bearer <token>` header, or None.

    Shared by `site_token_key` (below) and any router that authenticates public
    widget requests via a site token carried in this header — e.g.
    `routers/sessions.py::submit_feedback`.
    """
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None


def site_token_key(request: Request) -> str:
    """slowapi key_func: bucket per site_token (falls back to client IP).

    Some public routes expose `site_token` as a path parameter
    (`/api/chat/{site_token}/stream`); others (e.g. the widget feedback
    endpoint) carry it in the `Authorization: Bearer <token>` header or a
    `site_token` query param instead. Check all three, in that order, so every
    public/embeddable route gets genuine per-tenant bucketing rather than
    silently degrading to IP. Only when none is present do we fall back to IP,
    which keeps the default rate-limit contract intact for callers that never
    carry a token at all.
    """
    token = None
    try:
        token = request.path_params.get("site_token")
    except Exception:
        token = None
    if not token:
        token = extract_bearer_token(request.headers.get("authorization"))
    if not token:
        try:
            token = request.query_params.get("site_token")
        except Exception:
            token = None
    if token:
        return f"site:{token}"
    return get_remote_address(request)


def client_ip_key(request: Request) -> str:
    """slowapi key_func: bucket per client IP, namespaced `ip:<addr>`.

    Stacked on the public endpoints alongside `site_token_key` as the abuse
    ceiling a caller can't rotate away (see the module docstring).

    The `ip:` prefix is not cosmetic. slowapi derives a storage bucket from
    (limit string, key, route), so this key would share a bucket with
    `site_token_key`'s bare-IP fallback on any route where the two limits are
    configured with the same limit string — a tokenless request would then spend
    two hits from one bucket. Namespacing keeps the two limits independent
    whatever strings they're configured with.
    """
    return f"ip:{get_remote_address(request)}"


def ws_client_ip(websocket: WebSocket) -> str:
    """Peer address of a WebSocket connection, matching slowapi's `get_remote_address`.

    Both read the address ASGI put on the scope, and uvicorn's proxy-headers
    middleware rewrites that for `websocket` scopes as well as `http` ones (it
    branches on `scope["type"] in ("http", "websocket")`), gated on
    `FORWARDED_ALLOW_IPS`. So the handshake is exactly as trustworthy an address
    source as the HTTP path — no weaker, and no reason to read `X-Forwarded-For`
    here, which would be spoofable by any client.

    Falls back to `127.0.0.1` when the scope carries no client, which is both
    what `get_remote_address` does and what in-process test doubles present.
    """
    client = getattr(websocket, "client", None)
    host = getattr(client, "host", None)
    return host or "127.0.0.1"


class _SlidingWindow:
    """Sliding-window counter over a bounded registry of keys.

    Shared by the two WebSocket limiters below, which differ only in what they
    key on and how long their buckets are allowed to live.
    """

    # Sweep-interval: the global stale-bucket purge is O(N) over the whole dict,
    # so run it only once every SWEEP_EVERY calls. Correctness of the caller's
    # own bucket is unaffected — the per-key filter in `_hit` already expires
    # stale timestamps on every call.
    SWEEP_EVERY = 100

    # Hard cap on tracked keys. The sweep alone bounds a *quiet* registry, but
    # nothing stops a burst of distinct keys arriving faster than they expire,
    # so cap the dict outright — same reasoning as `_session_resume_locks` in
    # `routers/chat.py`. See `_evict` for why the eviction order matters.
    #
    # Read this as a bound on *keys*, not on memory: each key holds up to `max`
    # timestamps, and `max` differs sharply per subclass. At the session
    # limiter's 20 the worst case is 200k floats; at the ceiling's configured
    # 300 it is 3M — an order of magnitude more than the key count alone
    # suggests. Both are unreachable in practice (they need that many distinct
    # keys live within one window), but size any change to MAX_KEYS against the
    # subclass with the largest `max`, not against this number.
    MAX_KEYS = 10_000

    # Low-water mark for `_evict`: once over `MAX_KEYS`, trim down to this
    # fraction of it rather than back to the cap exactly. Trimming to the cap
    # leaves the registry one admission from overflowing again, so *every*
    # subsequent new key would pay for a full `sorted()` over MAX_KEYS entries —
    # the eviction path turning into its own CPU amplifier under precisely the
    # distributed flood the cap exists to blunt. At 0.9 the sort is paid once per
    # ~1,000 admissions instead of once per admission, and the extra ~1,000 keys
    # discarded per pass are the coldest ones, which is who `_evict` was going to
    # reach for next anyway.
    EVICT_TO_FRACTION = 0.9

    def __init__(self, window_seconds: int, max_requests: int) -> None:
        self.window = window_seconds
        self.max = max_requests
        self._timestamps: dict[str, list[float]] = {}
        # Eviction order only: which key was *seen* least recently, allowed or
        # refused. Distinct from the timestamps above, which record allowed hits
        # alone — a key sitting at its limit stops accruing those but is the last
        # one we want to evict. A monotonic counter rather than a clock reading
        # because ties matter here: `time()` on Windows can hand out the same
        # value to a whole burst of calls, and a stable sort over tied keys falls
        # back to insertion order — evicting the busiest key, which is the oldest
        # entry, first. That is the opposite of what `_evict` is for.
        self._last_seen_seq: dict[str, int] = {}
        self._seq: int = 0
        self._calls_since_sweep: int = 0

    def bucket_count(self) -> int:
        """Number of tracked keys — for tests / introspection."""
        return len(self._timestamps)

    def _forget(self, key: str) -> None:
        """Single removal path, so the two dicts can't drift apart."""
        self._timestamps.pop(key, None)
        self._last_seen_seq.pop(key, None)

    def _sweep(self, now: float, keep: str) -> None:
        """Drop every key whose window has fully expired."""
        stale = [k for k, ts in self._timestamps.items() if k != keep and all(now - t >= self.window for t in ts)]
        for k in stale:
            self._forget(k)

    def _evict(self, now: float, keep: str) -> None:
        """Force the registry back under MAX_KEYS: expired keys first, then coldest.

        Ordering by `_last_seen_seq` rather than by the newest allowed hit is
        what keeps eviction from becoming a way to shed one's own limit: a key
        that is being refused over and over is the most recently *seen* key
        there is, so it is evicted last rather than first.

        Two-level trim. The expiry sweep is cheap and non-destructive, so if it
        alone brings the registry back under the cap we stop there and no live
        key is dropped. Only when real, unexpired keys are still over the cap do
        we sort, and then we trim to `EVICT_TO_FRACTION` of it rather than to the
        cap — see that constant for why the headroom matters more than the ~1,000
        extra cold keys it costs.
        """
        self._sweep(now, keep)
        if len(self._timestamps) <= self.MAX_KEYS:
            return
        target = max(1, int(self.MAX_KEYS * self.EVICT_TO_FRACTION))
        overflow = len(self._timestamps) - target
        if overflow <= 0:
            return
        coldest = sorted((k for k in self._timestamps if k != keep), key=lambda k: self._last_seen_seq.get(k, 0))
        for k in coldest[:overflow]:
            self._forget(k)

    def _hit(self, key: str) -> bool:
        now = time()
        self._seq += 1
        self._last_seen_seq[key] = self._seq

        # Amortised global sweep: only run every SWEEP_EVERY calls so we aren't
        # O(N) per message at scale. Per-bucket expiry below handles correctness
        # for the caller's own key.
        self._calls_since_sweep += 1
        if self._calls_since_sweep >= self.SWEEP_EVERY:
            self._calls_since_sweep = 0
            self._sweep(now, keep=key)

        timestamps = [t for t in self._timestamps.get(key, []) if now - t < self.window]
        allowed = len(timestamps) < self.max
        if allowed:
            timestamps.append(now)
        self._timestamps[key] = timestamps
        if len(self._timestamps) > self.MAX_KEYS:
            self._evict(now, keep=key)
        return allowed


class SiteTokenWSRateLimiter(_SlidingWindow):
    """Sliding-window rate limiter keyed by (site_token, session_id).

    Used for WebSocket messages, which slowapi doesn't cover. Keeping one
    bucket per (token, session) means per-tenant isolation AND per-visitor
    fairness within a tenant. Sessions without a token fall back to session-only
    keying, matching legacy behaviour.

    Both halves of that key are client-supplied, so this limiter carries
    fairness but not abuse resistance: a client that reconnects gets a fresh
    session id and therefore a fresh bucket. `ClientIPWSRateLimiter` below is the
    ceiling a reconnect can't reset, and the two stack exactly as the two
    slowapi limits do on the HTTP routes (see the module docstring).
    """

    def __init__(self, window_seconds: int = 60, max_requests: int = 20) -> None:
        super().__init__(window_seconds, max_requests)

    @staticmethod
    def _key(session_id: str, site_token: str | None) -> str:
        return f"{site_token}:{session_id}" if site_token else session_id

    def is_allowed(self, session_id: str, site_token: str | None = None) -> bool:
        return self._hit(self._key(session_id, site_token))

    def cleanup(self, session_id: str, site_token: str | None = None) -> None:
        """Drop this session's bucket when its connection ends.

        Safe to do eagerly: the session id died with the connection, so nothing
        can present it again and there is no allowance to reset. That is exactly
        what is *not* true of the per-address ceiling below.
        """
        self._forget(self._key(session_id, site_token))


class ClientIPWSRateLimiter(_SlidingWindow):
    """Sliding-window ceiling on WebSocket messages, keyed by peer address.

    The WS counterpart of `client_ip_key`: the peer address is the one
    identifier a client that reconnects (fresh session id) or presents a
    different site_token cannot shed, so it is what makes the per-message
    allowance actually bind.

    Deliberately **not** cleaned up on disconnect. `SiteTokenWSRateLimiter`'s
    buckets die with their session; these have to outlive the connection or a
    reconnect would reset the very ceiling they exist to impose. They expire by
    time instead — the amortised sweep drops any address idle for a full window
    — with `MAX_KEYS` as the backstop for a burst of distinct addresses.
    """

    def __init__(self, window_seconds: int = 60, max_requests: int = 300) -> None:
        super().__init__(window_seconds, max_requests)

    def is_allowed(self, client_ip: str) -> bool:
        return self._hit(f"ip:{client_ip}")


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


# Process-wide WebSocket per-address ceiling. It lives here rather than beside
# the per-session limiter in `routers/chat.py` because it must outlive every
# individual connection — the router only ever reads it through the accessor.
def _default_ws_ip_ceiling() -> tuple[int, int]:
    """(window_seconds, max_messages) for the WS per-address ceiling.

    Its own key, `rate_limit.ws_public_ip`, rather than the HTTP routes'
    `public_ip`. The two carry identical work per event — one LLM turn — but a
    ceiling is sized by the legitimate aggregate rate at the granularity it keys
    on, and that differs: the widget speaks WebSocket exclusively, so every
    visitor behind a shared address lands on this limit, while `public_ip`'s
    routes carry only direct API consumers. `backend/config.py` carries the
    arithmetic.

    Parsed with the parser slowapi itself uses, so the WS ceiling stays
    expressible in the same units as every other `rate_limit` entry. Falls back
    to the documented 300/minute when settings or the string are unavailable,
    mirroring `_default_sse_cap`.
    """
    try:
        from config import settings

        item = parse(settings.rate_limit_ws_public_ip)
        return int(item.get_expiry()), int(item.amount)
    except Exception:
        return 60, 300


_ws_ip_ceiling = ClientIPWSRateLimiter(*_default_ws_ip_ceiling())


def get_ws_ip_ceiling() -> ClientIPWSRateLimiter:
    """The live per-address WS ceiling. Read it per message, never cache it —
    `_reset_ws_ip_ceiling_for_tests` rebinds the instance."""
    return _ws_ip_ceiling


def _reset_ws_ip_ceiling_for_tests(window_seconds: int | None = None, max_requests: int | None = None) -> None:
    """Test helper: rebuild the ceiling, optionally resized.

    The ceiling is process-global, so the suite resets it between tests (see the
    autouse fixture in `tests/conftest.py`); ceiling tests additionally shrink it
    so they can reach it without driving a full window's worth of real chat turns
    (300 at the configured `rate_limit.ws_public_ip`).
    """
    global _ws_ip_ceiling
    window, cap = _default_ws_ip_ceiling()
    _ws_ip_ceiling = ClientIPWSRateLimiter(
        window_seconds=window if window_seconds is None else window_seconds,
        max_requests=cap if max_requests is None else max_requests,
    )
