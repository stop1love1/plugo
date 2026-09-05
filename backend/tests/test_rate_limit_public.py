"""Rate limiting on the two public (site-token) endpoints.

`POST /api/chat/{site_token}/stream` and `POST /api/sessions/{id}/feedback` are
reachable by any embedder's visitors, and both carry two stacked slowapi limits:
one keyed by site_token (tenant fairness) and one keyed by client IP (the
ceiling a caller can't rotate away, since the site_token is caller-supplied).

These tests assert that slowapi enforces *both* — that neither decorator
silently wins — by making each limit the one that binds in turn:

* rotate the site_token every request, so only the per-IP limit can fire;
* hold the site_token still and stay under the per-IP ceiling, so only the
  per-token limit can fire.

Both cases also vary the path segment they can (the session_id on the feedback
route, the site_token on the SSE one), which is what pins `key_style="endpoint"`
in `limiter.py`: slowapi's "url" default folds the request path into the bucket
scope, and every public route here has a caller-supplied value in its path.

**Isolation.** slowapi's limiter and its storage are process-global, so a test
that fills a bucket can 429 an unrelated later test. Every test here therefore
(a) enables the limiter only inside `_rate_limiting_enabled()`, which disables it
again in a `finally`, (b) resets the limiter storage on both sides of the test,
and (c) drives its requests from an RFC 5737 documentation IP unique to that
test, using site tokens unique to that test — so its buckets are unreachable
from any other test even if the reset were skipped.

The rest of the suite is covered by the autouse `_disable_rate_limiter` fixture
in conftest.py, so it was already safe from us; the reset is what keeps us safe
from `test_auth.py::test_login_is_rate_limited`, the one other test that enables
the limiter and leaves its buckets behind.
"""

import contextlib
from collections.abc import AsyncIterator, Callable, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from limits import parse

from config import settings

FEEDBACK_BODY = {"message_index": 0, "rating": "up"}


def _limit_amount(limit_string: str) -> int:
    """Requests allowed per window by a slowapi limit string ("120/minute" -> 120).

    Parsed with the same parser slowapi uses, so these tests follow config.json
    instead of hard-coding numbers that could drift out of sync with it.
    """
    return parse(limit_string).amount


def _site_token_headers(token: str) -> dict[str, str]:
    """Widget auth for the feedback endpoint: the site token as a bearer token."""
    return {"Authorization": f"Bearer {token}"}


@contextlib.contextmanager
def _rate_limiting_enabled() -> Iterator[None]:
    """Turn the process-global limiter on for one test, leaving no state behind."""
    from main import limiter

    limiter.reset()
    limiter.enabled = True
    try:
        yield
    finally:
        limiter.enabled = False
        limiter.reset()


@pytest.fixture
async def clients_by_ip(client: AsyncClient) -> AsyncIterator[Callable[[str], AsyncClient]]:
    """Factory for test clients that present a chosen source IP.

    slowapi reads the peer address off the ASGI scope, which httpx's
    ASGITransport takes from its `client` argument — that is the only way to
    drive the per-IP limit from more than one address in-process. Depends on the
    shared `client` fixture for its test-database setup side effect.
    """
    from main import app

    created: list[AsyncClient] = []

    def _make(ip: str) -> AsyncClient:
        ac = AsyncClient(transport=ASGITransport(app=app, client=(ip, 12345)), base_url="http://test")
        created.append(ac)
        return ac

    yield _make
    for ac in created:
        await ac.aclose()


@pytest.mark.asyncio
async def test_feedback_ip_ceiling_survives_site_token_rotation(
    clients_by_ip: Callable[[str], AsyncClient],
) -> None:
    """A caller varying the site_token every request must still meet the per-IP ceiling.

    Every request carries a fresh token, so the per-token bucket holds exactly
    one hit and can never fire — only the per-IP limit can produce the 429.

    The session_id in the path varies too, deliberately: slowapi's bucket scope
    is the endpoint only because `limiter.py` sets `key_style="endpoint"`. Under
    its "url" default the path would be part of the scope and this rotation
    would mint a fresh bucket per request no matter how the limit is keyed.
    """
    ip_limit = _limit_amount(settings.rate_limit_public_ip)
    caller = clients_by_ip("203.0.113.11")

    with _rate_limiting_enabled():
        statuses = [
            (
                await caller.post(
                    f"/api/sessions/no-such-session-{i}/feedback",
                    json=FEEDBACK_BODY,
                    headers=_site_token_headers(f"feedback-rotating-token-{i}"),
                )
            ).status_code
            for i in range(ip_limit + 1)
        ]

    # 404 (unknown session), not 429: these reached the endpoint body, so the
    # final 429 is the limiter binding and not some earlier rejection.
    assert set(statuses[:ip_limit]) == {404}, f"expected the allowance to reach the endpoint, got {set(statuses)}"
    assert statuses[ip_limit] == 429, f"token rotation lifted the per-IP ceiling: request #{ip_limit + 1} was allowed"


@pytest.mark.asyncio
async def test_sse_ip_ceiling_survives_site_token_rotation(
    clients_by_ip: Callable[[str], AsyncClient],
) -> None:
    """Same for the SSE chat stream, whose site_token is a path parameter.

    `acquire_sse_slot` doesn't cover this: it is keyed by site_token too, so a
    rotating caller gets a fresh slot pool per token, and it caps concurrency
    rather than request rate either way.
    """
    ip_limit = _limit_amount(settings.rate_limit_public_ip)
    caller = clients_by_ip("203.0.113.12")

    with _rate_limiting_enabled():
        statuses = [
            (
                await caller.post(
                    f"/api/chat/sse-rotating-token-{i}/stream",
                    json={"message": "hello"},
                )
            ).status_code
            for i in range(ip_limit + 1)
        ]

    # 404 "Invalid site token" — the endpoint body ran and rejected the token.
    assert set(statuses[:ip_limit]) == {404}, f"expected the allowance to reach the endpoint, got {set(statuses)}"
    assert statuses[ip_limit] == 429, f"token rotation lifted the per-IP ceiling: request #{ip_limit + 1} was allowed"


@pytest.mark.asyncio
async def test_feedback_site_token_limit_fires_below_the_ip_ceiling(
    clients_by_ip: Callable[[str], AsyncClient],
) -> None:
    """Tenant fairness survives the stacking, and the per-token limit still binds.

    One tenant exhausts its own allowance from one IP. That must 429 it while
    leaving both a different tenant on the same IP and a different tenant on a
    different IP untouched — which is only true if the per-token limit is the
    one that fired.

    The noisy tenant varies the session_id in the path as it goes, so this also
    pins the endpoint-scoped bucket (see the sibling test): under slowapi's
    "url" default the per-token limit would never bind here either.
    """
    token_limit = _limit_amount(settings.rate_limit_default)
    ip_limit = _limit_amount(settings.rate_limit_public_ip)
    assert token_limit < ip_limit, (
        f"this test only discriminates while the per-token limit binds first "
        f"({token_limit} vs per-IP {ip_limit}) — adjust config.json → rate_limit"
    )

    noisy = clients_by_ip("203.0.113.13")
    quiet = clients_by_ip("203.0.113.14")

    with _rate_limiting_enabled():
        statuses = [
            (
                await noisy.post(
                    f"/api/sessions/no-such-session-{i}/feedback",
                    json=FEEDBACK_BODY,
                    headers=_site_token_headers("noisy-tenant"),
                )
            ).status_code
            for i in range(token_limit + 1)
        ]
        # Same IP, different tenant: allowed, so the 429 above came from the
        # per-token bucket and the per-IP bucket still has headroom.
        neighbour_same_ip = await noisy.post(
            "/api/sessions/no-such-session/feedback",
            json=FEEDBACK_BODY,
            headers=_site_token_headers("quiet-tenant-a"),
        )
        # Different tenant, different IP: untouched by the noisy tenant.
        neighbour_other_ip = await quiet.post(
            "/api/sessions/no-such-session/feedback",
            json=FEEDBACK_BODY,
            headers=_site_token_headers("quiet-tenant-b"),
        )

    assert set(statuses[:token_limit]) == {404}, f"expected the allowance to reach the endpoint, got {set(statuses)}"
    assert statuses[token_limit] == 429, "the per-token limit no longer fires — did the per-IP limit override it?"
    assert neighbour_same_ip.status_code == 404, "a second tenant on the noisy tenant's IP was starved"
    assert neighbour_other_ip.status_code == 404, "a second tenant on its own IP was starved"


@pytest.mark.asyncio
async def test_sse_site_token_limit_fires_below_the_ip_ceiling(
    clients_by_ip: Callable[[str], AsyncClient],
) -> None:
    """The same for the SSE stream's per-token limit, which no other test binds.

    Its sibling above rotates the token, so only the per-IP ceiling can fire
    there; `test_chat_sse.py` deliberately doesn't exercise the 429 either.
    Without this, deleting `@limiter.limit(settings.rate_limit_chat, ...)` from
    the route would leave the whole suite green — one of the four decorators
    this task turns on would be unguarded.
    """
    token_limit = _limit_amount(settings.rate_limit_chat)
    ip_limit = _limit_amount(settings.rate_limit_public_ip)
    assert token_limit < ip_limit, (
        f"this test only discriminates while the per-token limit binds first "
        f"({token_limit} vs per-IP {ip_limit}) — adjust config.json → rate_limit"
    )

    caller = clients_by_ip("203.0.113.16")

    with _rate_limiting_enabled():
        statuses = [
            (
                await caller.post(
                    "/api/chat/sse-noisy-tenant/stream",
                    json={"message": "hello"},
                )
            ).status_code
            for _ in range(token_limit + 1)
        ]
        # Same IP, a different tenant: allowed, so what fired above was the
        # per-token bucket and the per-IP ceiling still has headroom.
        neighbour_same_ip = await caller.post(
            "/api/chat/sse-quiet-tenant/stream",
            json={"message": "hello"},
        )

    assert set(statuses[:token_limit]) == {404}, f"expected the allowance to reach the endpoint, got {set(statuses)}"
    assert statuses[token_limit] == 429, "the SSE per-token limit no longer fires — was its decorator dropped?"
    assert neighbour_same_ip.status_code == 404, "a second tenant sharing the noisy tenant's IP was starved"


@pytest.mark.asyncio
async def test_bursty_dashboard_route_is_not_rate_limited(
    clients_by_ip: Callable[[str], AsyncClient],
    auth_headers: dict[str, str],
) -> None:
    """An admin route the dashboard calls once per rendered item must not be limited.

    The Flows page renders one screenshot request per step, so this route is
    reached in bursts. `key_style="endpoint"` means every call to it would share
    a single per-IP bucket if it ever came under a per-window limit — a 20-step
    flow rendered three times in a minute would then 429 the admin on their own
    dashboard. Nothing limits it today: it carries no `@limiter.limit(...)`, and
    slowapi reaches a route only through that decorator or `SlowAPIMiddleware`,
    which main.py doesn't install.

    Two ways that could change, and this test covers both:

    * someone decorates this route without weighing its call pattern — the
      burst below outruns any per-window limit they'd plausibly reach for;
    * `default_limits` comes back to `limiter.py` *and* someone installs that
      middleware, which together put every route under one bucket. Only the
      pair is dangerous, and the limits list is the half a test can see, so the
      assertion below pins it empty. (It was non-empty until the argument was
      removed as misleading — see the comment in `limiter.py`.)
    """
    from main import limiter

    burst = _limit_amount(settings.rate_limit_default) + 1
    admin = clients_by_ip("203.0.113.15")

    with _rate_limiting_enabled():
        statuses = [
            (
                await admin.get(
                    f"/api/flows/screenshots/flow-1/step-{i}.png",
                    headers=auth_headers,
                )
            ).status_code
            for i in range(burst)
        ]

    # 404 (no such screenshot file) — the request reached the handler every time.
    assert set(statuses) == {404}, f"a {burst}-request dashboard burst was refused: {sorted(set(statuses))}"
    assert limiter._default_limits == [], (
        "limiter.py grew default limits again — harmless alone, but installing "
        "SlowAPIMiddleware would then put this burst route under one per-IP bucket"
    )
