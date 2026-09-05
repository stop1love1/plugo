"""The WebSocket transport's per-address message ceiling.

`SiteTokenWSRateLimiter` buckets per `(site_token, session_id)`, and **both** halves
are client-supplied: the token arrives in the init frame or the URL path, and the
session id is minted fresh for every connection. So the 20-per-60s window it enforces
binds within one connection and nowhere else — reconnect and the bucket is new. That is
the same key-rotation hole the two public HTTP routes had before their per-IP limit was
stacked on (`test_rate_limit_public.py`), and `ClientIPWSRateLimiter` closes it here for
the same reason: the peer address is the one identifier a reconnecting client can't shed.

**Showing which limiter fired.** "The client was refused" is true of both limiters, so
every test below pins the *bucket*, never just the refusal:

* the ceiling tests keep each connection to two messages — an order of magnitude under
  `WS_RATE_LIMIT_MAX` — so the per-session window provably cannot be what fired, and then
  show a neighbour connection from a *different address* sailing through;
* the per-session test does the mirror image: it overruns one connection's window while
  the ceiling has thousands of messages of headroom, and shows a neighbour connection
  from the *same address* sailing through.

**Isolation.** The ceiling is process-global and, unlike slowapi's limiter, has no
`enabled` switch to turn off. `conftest.py`'s autouse `_reset_ws_ip_ceiling` fixture
rebuilds it before every test; these tests additionally resize it inside their own bodies
(reaching the configured ceiling through the real turn loop would mean 300 chat turns) and drive
their traffic from an RFC 5737 documentation address unique to the test, so their buckets
are unreachable from any other test even if the reset were skipped.
"""

import pytest
from limits import parse

from agent.core import ChatAgent
from config import settings
from repositories import Repositories, create_repos
from routers.chat import WS_RATE_LIMIT_MAX, WS_RATE_LIMITED_MESSAGE, _run_websocket_chat, _ws_rate_limiter
from tests.conftest import _FakeWebSocket, _StubProvider
from utils.rate_limit import ClientIPWSRateLimiter, _reset_ws_ip_ceiling_for_tests, get_ws_ip_ceiling


def _patch_stub_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the turn loop off the network: stub provider, no retrieval."""
    monkeypatch.setattr("agent.core.get_llm_provider", lambda *a, **k: _StubProvider())

    async def _fake_build_system_prompt(
        self: ChatAgent,
        query: str,
        page_context: dict | None = None,
        repos: object = None,
        visitor_id: str | None = None,
        conversation_summary: str | None = None,
    ) -> tuple[str, list[dict], bool]:
        self.last_citations = []
        self.last_tool_calls = []
        return "system prompt", [], True

    monkeypatch.setattr(ChatAgent, "_build_system_prompt", _fake_build_system_prompt)


async def _run_ws(
    site: dict,
    client_host: str,
    messages: list[str],
    site_token: str | None = None,
    first_data: dict | None = None,
) -> _FakeWebSocket:
    """Drive one full WS connection from `client_host`, then let it disconnect.

    `site_token` defaults to the site's own; the ceiling tests vary it to show that
    rotating it doesn't lift the ceiling. It is the only thing `_run_websocket_chat`
    uses the token for, so passing a different string is exactly what a caller holding
    a second tenant's token looks like to the limiters.

    `first_data` defaults to a bare `init` frame, so every message in `messages` goes
    through the turn loop. Pass a frame carrying a `message` instead to exercise the
    pre-loop path, which handles one message before the loop is ever entered.
    """
    websocket = _FakeWebSocket(frames=[{"message": m} for m in messages], client_host=client_host)
    ws_repos = await create_repos()
    await _run_websocket_chat(
        websocket,
        ws_repos,
        {**site, "is_approved": True},
        site_token if site_token is not None else site["token"],
        first_data={"type": "init"} if first_data is None else first_data,
    )
    return websocket


def _refusals(websocket: _FakeWebSocket) -> int:
    return sum(1 for f in websocket.sent if f.get("type") == "error" and f.get("message") == WS_RATE_LIMITED_MESSAGE)


def _answered(websocket: _FakeWebSocket) -> int:
    """Turns that completed — the loop emits exactly one `end` frame per answered turn."""
    return sum(1 for f in websocket.sent if f.get("type") == "end")


def _session_id(websocket: _FakeWebSocket) -> str:
    return websocket.sent[0]["session_id"]


@pytest.mark.asyncio
async def test_reconnecting_with_a_fresh_session_cannot_reset_the_ip_ceiling(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three connections, two messages each, against a four-message ceiling.

    Every connection gets a brand-new session id and therefore a brand-new
    `SiteTokenWSRateLimiter` bucket, so under the per-session window alone all six
    messages would be answered. Two of them must not be.
    """
    _patch_stub_agent(monkeypatch)
    _reset_ws_ip_ceiling_for_tests(window_seconds=60, max_requests=4)

    sockets = [await _run_ws(test_site, "203.0.113.21", ["q1", "q2"]) for _ in range(3)]

    # Each connection really did start fresh — otherwise this proves nothing about
    # reconnects, only about one long-lived bucket.
    assert len({_session_id(ws) for ws in sockets}) == 3
    # ...and each stayed an order of magnitude under its own window, so the refusals
    # below cannot have come from the per-session limiter.
    assert WS_RATE_LIMIT_MAX > 2

    assert [_answered(ws) for ws in sockets] == [2, 2, 0]
    assert [_refusals(ws) for ws in sockets] == [0, 0, 2]

    # Same tenant, same fresh-session pattern, different address: fully answered. The
    # bucket that fired is keyed on the peer address and nothing else.
    neighbour = await _run_ws(test_site, "203.0.113.22", ["q1", "q2"])
    assert _answered(neighbour) == 2
    assert _refusals(neighbour) == 0


@pytest.mark.asyncio
async def test_ws_ip_ceiling_survives_site_token_rotation(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller varying the site_token every connection must still meet the ceiling.

    The direct analogue of `test_rate_limit_public.py`'s rotation tests. With a fresh
    token *and* a fresh session on every connection, the per-session bucket holds two
    hits at most and can never fire — only the per-address ceiling can produce these
    refusals.
    """
    _patch_stub_agent(monkeypatch)
    _reset_ws_ip_ceiling_for_tests(window_seconds=60, max_requests=4)

    sockets = [
        await _run_ws(test_site, "203.0.113.23", ["q1", "q2"], site_token=f"rotating-token-{i}") for i in range(3)
    ]

    assert [_answered(ws) for ws in sockets] == [2, 2, 0]
    assert [_refusals(ws) for ws in sockets] == [0, 0, 2]


@pytest.mark.asyncio
async def test_ws_ip_ceiling_does_not_starve_another_tenant_on_another_source(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tenant fairness survives the stacking.

    One tenant exhausting the ceiling from its own address must leave a different
    tenant on a different address untouched — the ceiling is a per-source cap, not a
    global one, so it can't be used to starve a neighbour.
    """
    _patch_stub_agent(monkeypatch)
    _reset_ws_ip_ceiling_for_tests(window_seconds=60, max_requests=2)

    noisy = await _run_ws(test_site, "203.0.113.24", ["q1", "q2", "q3"], site_token="noisy-tenant")
    assert _answered(noisy) == 2
    assert _refusals(noisy) == 1

    quiet = await _run_ws(test_site, "203.0.113.25", ["q1", "q2"], site_token="quiet-tenant")
    assert _answered(quiet) == 2
    assert _refusals(quiet) == 0


@pytest.mark.asyncio
async def test_ceiling_covers_the_message_carried_in_the_connection_frame(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One message per connection, carried in the first frame, must still be counted.

    `_run_websocket_chat` answers a first frame that carries a `message` (rather than
    `type: "init"`) *before* entering the turn loop, so that message never reaches the
    loop's rate-limit check. Connect, send one message, disconnect, repeat would
    otherwise walk straight past the ceiling — the reconnect bypass in its purest form,
    and the tests above would not see it because they all open with an `init` frame.
    """
    _patch_stub_agent(monkeypatch)
    _reset_ws_ip_ceiling_for_tests(window_seconds=60, max_requests=2)

    sockets = [await _run_ws(test_site, "203.0.113.28", [], first_data={"message": f"q{i}"}) for i in range(3)]

    assert len({_session_id(ws) for ws in sockets}) == 3
    assert [_answered(ws) for ws in sockets] == [1, 1, 0]
    assert [_refusals(ws) for ws in sockets] == [0, 0, 1]

    # One message on a fresh session can never trip the per-session window, and a
    # connection from another address is answered — so the refusal is the ceiling's.
    neighbour = await _run_ws(test_site, "203.0.113.29", [], first_data={"message": "q"})
    assert _answered(neighbour) == 1
    assert _refusals(neighbour) == 0


@pytest.mark.asyncio
async def test_per_session_window_still_binds_below_the_ip_ceiling(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The existing 20-per-60s window must keep firing within a single connection.

    The mirror image of the tests above: the ceiling is raised far out of reach, so the
    single refusal here can only be the per-session window. The neighbour check is what
    proves it — a second connection from the *same* address is answered, which would be
    impossible if the ceiling were what fired.
    """
    _patch_stub_agent(monkeypatch)
    _reset_ws_ip_ceiling_for_tests(window_seconds=60, max_requests=1000)

    overrun = await _run_ws(test_site, "203.0.113.26", [f"q{i}" for i in range(WS_RATE_LIMIT_MAX + 1)])
    assert _answered(overrun) == WS_RATE_LIMIT_MAX
    assert _refusals(overrun) == 1

    neighbour = await _run_ws(test_site, "203.0.113.26", ["q1"])
    assert _answered(neighbour) == 1
    assert _refusals(neighbour) == 0


@pytest.mark.asyncio
async def test_disconnect_drops_the_session_bucket_but_keeps_the_ip_ceiling(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two halves of the cleanup contract, asserted together.

    `_run_websocket_chat`'s `finally` calls `cleanup` for the per-session bucket, so
    twelve connect/disconnect cycles must leave the session registry exactly where they
    found it — no leak. The ceiling's bucket for that address must survive all twelve,
    because a ceiling cleaned up on disconnect is a ceiling a reconnect resets.
    """
    _patch_stub_agent(monkeypatch)
    _reset_ws_ip_ceiling_for_tests(window_seconds=60, max_requests=100)
    ceiling = get_ws_ip_ceiling()

    baseline = _ws_rate_limiter.bucket_count()
    for _ in range(12):
        websocket = await _run_ws(test_site, "203.0.113.27", ["q1"])
        assert _answered(websocket) == 1

    assert _ws_rate_limiter.bucket_count() == baseline, "per-session buckets leaked across disconnects"
    assert ceiling.bucket_count() == 1, (
        "one address should hold exactly one ceiling bucket, however often it reconnects"
    )


def test_ip_ceiling_registry_is_bounded_and_evicts_the_coldest_first() -> None:
    """The ceiling's registry is capped, and the cap can't be used to shed a limit.

    Buckets here are never cleaned up on disconnect, so a burst of distinct addresses
    could grow the dict without bound — hence `MAX_KEYS`, following the bounded
    `_session_resume_locks` registry in `routers/chat.py`. Eviction orders by *last
    seen*, so an address being refused over and over is the freshest key in the dict and
    survives the churn; ordering by last allowed hit would have evicted it first and
    handed it a fresh allowance.

    (A flooder that goes quiet long enough for MAX_KEYS other addresses to be seen does
    lose its bucket. Reaching that needs thousands of distinct source addresses, each
    spending its own successful message — at which point the attacker no longer needs
    the eviction.)
    """
    limiter = ClientIPWSRateLimiter(window_seconds=60, max_requests=2)
    limiter.MAX_KEYS = 10

    assert limiter.is_allowed("198.51.100.1")
    assert limiter.is_allowed("198.51.100.1")
    assert not limiter.is_allowed("198.51.100.1")

    for i in range(2, 202):
        assert limiter.is_allowed(f"198.51.100.{i}"), "an unrelated address must not inherit the flooder's bucket"
        assert not limiter.is_allowed("198.51.100.1"), "registry churn reset the flooder's ceiling"

    assert limiter.bucket_count() <= limiter.MAX_KEYS
    assert not limiter.is_allowed("198.51.100.1")


def test_ws_ip_ceiling_uses_its_own_configured_limit() -> None:
    """The ceiling's allowance is `config.json → rate_limit.ws_public_ip`, not a literal.

    Its own key rather than the HTTP routes' `public_ip`. The per-event cost is
    identical — one LLM turn either way — but a ceiling is sized by the legitimate
    aggregate rate at the granularity it keys on, and the widget speaks WebSocket
    exclusively (`frontend/src/widget/ui/App.tsx`), so every visitor behind a shared
    address lands here while `public_ip`'s routes carry only direct API consumers.

    The tests above shrink the ceiling to reach it cheaply, so without this nothing
    would notice the configured value being ignored.
    """
    _reset_ws_ip_ceiling_for_tests()
    configured = parse(settings.rate_limit_ws_public_ip)
    ceiling = get_ws_ip_ceiling()

    assert ceiling.max == configured.amount
    assert ceiling.window == configured.get_expiry()


def test_ws_ip_ceiling_is_sized_for_shared_egress_addresses() -> None:
    """Pins the two sizing relationships `backend/config.py` argues from.

    Neither is arbitrary, and both are silently breakable by editing one number in
    config.json — which is exactly when someone should have to read the reasoning.

    * **Above one session's own window**, or the ceiling would pre-empt the fairness
      limit and a single well-behaved visitor would meet the abuse cap first. Same
      relationship the HTTP routes hold between `default`/`chat` and `public_ip`.
    * **Enough concurrent chatters behind one address.** The widget disables its input
      while a reply streams, so a visitor cannot exceed roughly 6 messages/minute; a
      corporate NAT or CGNAT block needs room for tens of them at once. Sizing this
      from the HTTP ceiling instead (120/minute) would leave ~20, which is where a
      NAT'd office starts seeing its messages silently refused.
    """
    ceiling = get_ws_ip_ceiling()
    per_minute = ceiling.max * 60 // ceiling.window

    assert per_minute > WS_RATE_LIMIT_MAX, (
        f"the per-address ceiling ({per_minute}/min) is at or below one session's own "
        f"window ({WS_RATE_LIMIT_MAX}/min) — it would fire before the fairness limit"
    )
    # 6/minute is the fastest a streaming-gated visitor can go; 40 of them at once is
    # the shared-egress headroom the value was chosen for.
    assert per_minute // 6 >= 40, (
        f"{per_minute}/min leaves room for only {per_minute // 6} simultaneously engaged "
        f"visitors behind one egress address — too tight for a NAT'd office; see the "
        f"sizing note on rate_limit_ws_public_ip in backend/config.py"
    )
