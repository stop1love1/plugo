"""Tests for the /api/analytics/* aggregation endpoints.

Strategy: seed chat sessions with deterministic timestamps so the day-bucket
assertions don't flake when the test runs near midnight. Every test creates
its own site to avoid cross-test contamination on shared counters.
"""

import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from repositories import Repositories


@pytest.fixture
async def analytics_site(db_repos):
    """Dedicated site per test so overview counts are isolated."""
    site = await db_repos.sites.create(
        {
            "name": "Analytics Site",
            "url": "https://analytics.example.com",
            "llm_provider": "claude",
            "llm_model": "claude-sonnet-4-20250514",
            "primary_color": "#6366f1",
            "greeting": "Hi!",
            "allowed_domains": "",
        }
    )
    yield site
    # Sessions cascade-delete with the site via FK.
    with contextlib.suppress(Exception):
        await db_repos.sites.delete(site["id"])


async def _seed_session(db_repos, site_id: str, messages: list[dict], started_at: datetime | None = None):
    """Insert a session with a known message list and (optionally) backdated start."""
    from database import async_session
    from models.chat import ChatSession

    # We need to force `started_at` to a backdated value for the
    # messages-per-day test; the repo.create() path stamps `now()`.
    async with async_session() as db:
        sess = ChatSession(
            id=str(uuid.uuid4()),
            site_id=site_id,
            visitor_id=f"vis-{uuid.uuid4().hex[:8]}",
            messages=messages,
            started_at=started_at or datetime.now(UTC),
            ended_at=datetime.now(UTC),
        )
        db.add(sess)
        await db.commit()
        return sess.id


def _msg(role: str, content: str, when: datetime) -> dict:
    return {"role": role, "content": content, "timestamp": when.isoformat()}


@pytest.mark.asyncio
async def test_overview_aggregates_three_sessions(client, auth_headers, db_repos, analytics_site):
    now = datetime.now(UTC)
    # 3 sessions, 2 + 4 + 6 = 12 messages.
    await _seed_session(
        db_repos,
        analytics_site["id"],
        [
            _msg("user", "q1", now),
            _msg("assistant", "a1", now),
        ],
    )
    await _seed_session(
        db_repos,
        analytics_site["id"],
        [
            _msg("user", "q1", now),
            _msg("assistant", "a1", now),
            _msg("user", "q2", now),
            _msg("assistant", "a2", now),
        ],
    )
    await _seed_session(
        db_repos,
        analytics_site["id"],
        [
            _msg("user", "q1", now),
            _msg("assistant", "a1", now),
            _msg("user", "q2", now),
            _msg("assistant", "a2", now),
            _msg("user", "q3", now),
            _msg("assistant", "a3", now),
        ],
    )

    r = await client.get(
        f"/api/analytics/overview?site_id={analytics_site['id']}&days=30",
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total_sessions"] == 3
    assert data["total_messages"] == 12
    assert data["avg_messages_per_session"] == 4.0


@pytest.mark.asyncio
async def test_overview_empty_site_returns_zeros(client, auth_headers, analytics_site):
    r = await client.get(
        f"/api/analytics/overview?site_id={analytics_site['id']}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total_sessions"] == 0
    assert data["total_messages"] == 0
    # 0/0 guard should give 0.0, not raise.
    assert data["avg_messages_per_session"] == 0.0


@pytest.mark.asyncio
async def test_overview_requires_auth(client, analytics_site):
    r = await client.get(f"/api/analytics/overview?site_id={analytics_site['id']}")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_messages_per_day_buckets_correctly(client, auth_headers, db_repos, analytics_site):
    now = datetime.now(UTC)
    today = now.replace(hour=12, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    # Two messages today, three yesterday.
    await _seed_session(
        db_repos,
        analytics_site["id"],
        [_msg("user", "today-1", today), _msg("assistant", "r1", today)],
        started_at=today,
    )
    await _seed_session(
        db_repos,
        analytics_site["id"],
        [
            _msg("user", "y-1", yesterday),
            _msg("assistant", "r1", yesterday),
            _msg("user", "y-2", yesterday),
        ],
        started_at=yesterday,
    )

    r = await client.get(
        f"/api/analytics/messages-per-day?site_id={analytics_site['id']}&days=7",
        headers=auth_headers,
    )
    assert r.status_code == 200
    arr = r.json()
    assert len(arr) == 7

    by_date = {row["date"]: row["messages"] for row in arr}
    assert by_date.get(today.strftime("%Y-%m-%d")) == 2
    assert by_date.get(yesterday.strftime("%Y-%m-%d")) == 3


@pytest.mark.asyncio
async def test_popular_questions_counts_duplicates(client, auth_headers, db_repos, analytics_site):
    now = datetime.now(UTC)
    # "What are your hours?" asked 3 times, "Where are you?" asked 1 time.
    for _ in range(3):
        await _seed_session(
            db_repos,
            analytics_site["id"],
            [
                _msg("user", "What are your hours?", now),
                _msg("assistant", "9-5", now),
            ],
        )
    await _seed_session(
        db_repos,
        analytics_site["id"],
        [
            _msg("user", "Where are you?", now),
            _msg("assistant", "Online.", now),
        ],
    )

    r = await client.get(
        f"/api/analytics/popular-questions?site_id={analytics_site['id']}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    items = r.json()
    top = items[0]
    assert top["question"] == "What are your hours?"
    assert top["count"] == 3


@pytest.mark.asyncio
async def test_knowledge_gaps_detects_apology_patterns(client, auth_headers, db_repos, analytics_site):
    now = datetime.now(UTC)
    # Gap indicator: "I don't have". Should be attributed to the preceding user message.
    await _seed_session(
        db_repos,
        analytics_site["id"],
        [
            _msg("user", "What colour is your logo?", now),
            _msg("assistant", "Sorry, I don't have that information.", now),
        ],
    )
    # Non-gap — answered confidently.
    await _seed_session(
        db_repos,
        analytics_site["id"],
        [
            _msg("user", "What is your name?", now),
            _msg("assistant", "Plugo.", now),
        ],
    )

    r = await client.get(
        f"/api/analytics/knowledge-gaps?site_id={analytics_site['id']}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    items = r.json()
    # Only the logo-question conversation should appear.
    assert any(i["question"] == "What colour is your logo?" for i in items)
    assert not any(i["question"] == "What is your name?" for i in items)


@pytest.mark.asyncio
async def test_knowledge_gaps_detects_default_vietnamese_fallback(
    client: AsyncClient, auth_headers: dict, db_repos: Repositories, analytics_site: dict
) -> None:
    """The bot's own default Vietnamese no-knowledge reply must be counted as a gap."""
    from agent.core import ChatAgent

    now = datetime.now(UTC)
    await _seed_session(
        db_repos,
        analytics_site["id"],
        [
            _msg("user", "Edusoft cung cấp giải pháp gì?", now),
            _msg("assistant", ChatAgent._DEFAULT_NO_KNOWLEDGE_VI, now),
        ],
    )
    # Non-gap Vietnamese answer — must not be flagged.
    await _seed_session(
        db_repos,
        analytics_site["id"],
        [
            _msg("user", "Văn phòng ở đâu?", now),
            _msg("assistant", "Văn phòng của chúng tôi ở Hà Nội.", now),
        ],
    )

    r = await client.get(
        f"/api/analytics/knowledge-gaps?site_id={analytics_site['id']}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    items = r.json()
    assert any(i["question"] == "Edusoft cung cấp giải pháp gì?" for i in items)
    assert not any(i["question"] == "Văn phòng ở đâu?" for i in items)


@pytest.mark.asyncio
async def test_knowledge_gaps_ignores_advice_addressed_to_the_visitor(
    client: AsyncClient, auth_headers: dict, db_repos: Repositories, analytics_site: dict
) -> None:
    """The Vietnamese indicators are pronoun-anchored: "if *you* don't know…" is a
    complete, helpful answer, not a knowledge gap. Only first-person forms count."""
    now = datetime.now(UTC)
    await _seed_session(
        db_repos,
        analytics_site["id"],
        [
            _msg("user", "Tôi tra cứu đơn hàng thế nào?", now),
            _msg("assistant", "Nếu bạn không biết mã đơn hàng, hãy kiểm tra email xác nhận nhé.", now),
        ],
    )
    await _seed_session(
        db_repos,
        analytics_site["id"],
        [
            _msg("user", "Cửa hàng có giao quốc tế không?", now),
            # "không rõ" unanchored — an indicator only in its first-person forms
            # ("tôi không rõ" / "mình không rõ"), which is exactly what must not match here.
            _msg("assistant", "Nếu bạn không rõ phí ship, bạn có thể xem bảng giá trên website.", now),
        ],
    )
    # First person — this one really is a gap.
    await _seed_session(
        db_repos,
        analytics_site["id"],
        [
            _msg("user", "Chính sách bảo hành thế nào?", now),
            _msg("assistant", "Xin lỗi, mình không biết chính sách bảo hành.", now),
        ],
    )

    r = await client.get(
        f"/api/analytics/knowledge-gaps?site_id={analytics_site['id']}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    flagged = {i["question"] for i in r.json()}
    assert "Chính sách bảo hành thế nào?" in flagged
    assert "Tôi tra cứu đơn hàng thế nào?" not in flagged
    assert "Cửa hàng có giao quốc tế không?" not in flagged


async def _seed_two_tools(db_repos: Repositories, site_id: str) -> None:
    for name in ("lookup", "search"):
        await db_repos.tools.create(
            {
                "site_id": site_id,
                "name": name,
                "description": "",
                "method": "GET",
                "url": f"https://api.example.com/{name}",
            }
        )


def _assistant_with_tools(content: str, when: datetime, tool_calls: list[dict]) -> dict:
    return {
        "role": "assistant",
        "content": content,
        "timestamp": when.isoformat(),
        "tool_calls": tool_calls,
    }


@pytest.mark.asyncio
async def test_tool_usage_counts_successful_invocation(
    client: AsyncClient, auth_headers: dict, db_repos: Repositories, analytics_site: dict
) -> None:
    """A persisted successful tool invocation is reported under `calls`, not `errors`."""
    await _seed_two_tools(db_repos, analytics_site["id"])

    now = datetime.now(UTC)
    await _seed_session(
        db_repos,
        analytics_site["id"],
        [
            _msg("user", "where is order 123?", now),
            _assistant_with_tools("It shipped yesterday.", now, [{"name": "lookup", "success": True}]),
        ],
    )

    r = await client.get(
        f"/api/analytics/tool-usage?site_id={analytics_site['id']}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    tools = r.json()
    assert len(tools) == 2
    by_name = {t["name"]: t for t in tools}
    assert by_name["lookup"]["calls"] == 1
    assert by_name["lookup"]["errors"] == 0
    assert by_name["search"]["calls"] == 0
    assert by_name["search"]["errors"] == 0


@pytest.mark.asyncio
async def test_tool_usage_counts_failed_invocation_as_error(
    client: AsyncClient, auth_headers: dict, db_repos: Repositories, analytics_site: dict
) -> None:
    """A failed invocation still counts as a call, and additionally as an error."""
    await _seed_two_tools(db_repos, analytics_site["id"])

    now = datetime.now(UTC)
    await _seed_session(
        db_repos,
        analytics_site["id"],
        [
            _msg("user", "search for hats", now),
            _assistant_with_tools(
                "Sorry, that lookup failed.",
                now,
                [{"name": "search", "success": False}, {"name": "search", "success": True}],
            ),
        ],
    )

    r = await client.get(
        f"/api/analytics/tool-usage?site_id={analytics_site['id']}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    by_name = {t["name"]: t for t in r.json()}
    assert by_name["search"]["calls"] == 2
    assert by_name["search"]["errors"] == 1
    assert by_name["lookup"]["calls"] == 0


@pytest.mark.asyncio
async def test_tool_usage_legacy_sessions_without_tool_data(
    client: AsyncClient, auth_headers: dict, db_repos: Repositories, analytics_site: dict
) -> None:
    """Sessions stored before tool recording existed have no tool key — report zeros, don't raise."""
    await _seed_two_tools(db_repos, analytics_site["id"])

    now = datetime.now(UTC)
    await _seed_session(
        db_repos,
        analytics_site["id"],
        [
            _msg("user", "hi", now),
            _msg("assistant", "Hello! How can I help?", now),
        ],
    )

    r = await client.get(
        f"/api/analytics/tool-usage?site_id={analytics_site['id']}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    tools = r.json()
    assert len(tools) == 2
    assert {t["name"] for t in tools} == {"lookup", "search"}
    assert all(t["calls"] == 0 and t["errors"] == 0 for t in tools)
    assert all(t["enabled"] is True for t in tools)
