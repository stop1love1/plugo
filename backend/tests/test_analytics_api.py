"""Tests for the /api/analytics/* aggregation endpoints.

Strategy: seed chat sessions with deterministic timestamps so the day-bucket
assertions don't flake when the test runs near midnight. Every test creates
its own site to avoid cross-test contamination on shared counters.
"""

import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest


@pytest.fixture
async def analytics_site(db_repos):
    """Dedicated site per test so overview counts are isolated."""
    site = await db_repos.sites.create({
        "name": "Analytics Site",
        "url": "https://analytics.example.com",
        "llm_provider": "claude",
        "llm_model": "claude-sonnet-4-20250514",
        "primary_color": "#6366f1",
        "greeting": "Hi!",
        "allowed_domains": "",
    })
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
    await _seed_session(db_repos, analytics_site["id"], [
        _msg("user", "q1", now),
        _msg("assistant", "a1", now),
    ])
    await _seed_session(db_repos, analytics_site["id"], [
        _msg("user", "q1", now), _msg("assistant", "a1", now),
        _msg("user", "q2", now), _msg("assistant", "a2", now),
    ])
    await _seed_session(db_repos, analytics_site["id"], [
        _msg("user", "q1", now), _msg("assistant", "a1", now),
        _msg("user", "q2", now), _msg("assistant", "a2", now),
        _msg("user", "q3", now), _msg("assistant", "a3", now),
    ])

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
        db_repos, analytics_site["id"],
        [_msg("user", "today-1", today), _msg("assistant", "r1", today)],
        started_at=today,
    )
    await _seed_session(
        db_repos, analytics_site["id"],
        [
            _msg("user", "y-1", yesterday), _msg("assistant", "r1", yesterday),
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
        await _seed_session(db_repos, analytics_site["id"], [
            _msg("user", "What are your hours?", now),
            _msg("assistant", "9-5", now),
        ])
    await _seed_session(db_repos, analytics_site["id"], [
        _msg("user", "Where are you?", now),
        _msg("assistant", "Online.", now),
    ])

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
    await _seed_session(db_repos, analytics_site["id"], [
        _msg("user", "What colour is your logo?", now),
        _msg("assistant", "Sorry, I don't have that information.", now),
    ])
    # Non-gap — answered confidently.
    await _seed_session(db_repos, analytics_site["id"], [
        _msg("user", "What is your name?", now),
        _msg("assistant", "Plugo.", now),
    ])

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
async def test_tool_usage_returns_tools_with_counts(client, auth_headers, db_repos, analytics_site):
    # Seed two tools, one with a matching "[Called X]" assistant message.
    await db_repos.tools.create({
        "site_id": analytics_site["id"],
        "name": "lookup",
        "description": "",
        "method": "GET",
        "url": "https://api.example.com/lookup",
    })
    await db_repos.tools.create({
        "site_id": analytics_site["id"],
        "name": "search",
        "description": "",
        "method": "GET",
        "url": "https://api.example.com/search",
    })

    now = datetime.now(UTC)
    await _seed_session(db_repos, analytics_site["id"], [
        _msg("user", "hi", now),
        # The analytics detector looks for the literal "[Called " substring.
        {"role": "assistant", "content": "[Called lookup] result", "timestamp": now.isoformat(), "tool_name": "lookup"},
    ])

    r = await client.get(
        f"/api/analytics/tool-usage?site_id={analytics_site['id']}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    tools = r.json()
    assert len(tools) == 2
    by_name = {t["name"]: t for t in tools}
    assert by_name["lookup"]["calls"] == 1
    assert by_name["search"]["calls"] == 0
