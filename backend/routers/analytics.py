"""Analytics router — aggregate stats from chat sessions."""

from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from auth import TokenData, get_current_user
from logging_config import logger
from repositories import Repositories, get_repos

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Cap on sessions pulled into memory for the message-scanning endpoints below.
# These read full message blobs, so an unbounded scan would OOM/timeout on a
# high-traffic site. The overview endpoint is unaffected — it aggregates at the
# DB layer. Bounded to the most recent sessions; truncation is logged, never silent.
ANALYTICS_MAX_SESSIONS = 5000


async def _load_sessions_capped(repos: Repositories, site_id: str, cutoff: datetime) -> list[dict]:
    sessions = await repos.chat_sessions.list_by_site_since(site_id, cutoff, limit=ANALYTICS_MAX_SESSIONS)
    if len(sessions) >= ANALYTICS_MAX_SESSIONS:
        logger.warning(
            "Analytics scan truncated to most-recent sessions",
            site_id=site_id,
            cap=ANALYTICS_MAX_SESSIONS,
        )
    return sessions


@router.get("/overview")
async def get_overview(
    site_id: str = Query(...),
    days: int = Query(default=30, ge=1, le=365),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Get overview stats: total sessions, messages, avg duration."""
    empty_overview = {
        "total_sessions": 0,
        "total_messages": 0,
        "avg_messages_per_session": 0.0,
        "avg_session_duration_seconds": 0,
    }
    try:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        stats = await repos.chat_sessions.aggregate_overview(site_id, cutoff)
        total_sessions = stats["total_sessions"]
        total_messages = stats["total_messages"]
        if total_sessions == 0:
            return empty_overview
        avg_messages = total_messages / total_sessions if total_sessions > 0 else 0.0
        return {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "avg_messages_per_session": round(avg_messages, 1),
            "avg_session_duration_seconds": round(stats["avg_session_duration_seconds"]),
        }
    except Exception as e:
        logger.error("Analytics overview error", error=str(e))
        return empty_overview


@router.get("/messages-per-day")
async def get_messages_per_day(
    site_id: str = Query(...),
    days: int = Query(default=30, ge=1, le=365),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Get daily message counts for chart."""
    try:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        sessions = await _load_sessions_capped(repos, site_id, cutoff)
        daily_counts: dict[str, int] = {}

        for s in sessions:
            messages = s.get("messages", [])
            for msg in messages:
                ts = msg.get("timestamp")
                if not ts:
                    continue
                if isinstance(ts, str):
                    try:
                        dt = datetime.fromisoformat(ts)
                    except ValueError:
                        continue
                else:
                    dt = ts
                # Ensure dt is timezone-aware for comparison with cutoff
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                if dt < cutoff:
                    continue
                day = dt.strftime("%Y-%m-%d")
                daily_counts[day] = daily_counts.get(day, 0) + 1

        # Fill in missing days
        result = []
        for i in range(days):
            day = (datetime.now(UTC) - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            result.append({"date": day, "messages": daily_counts.get(day, 0)})

        return result
    except Exception as e:
        logger.error("Analytics messages-per-day error", error=str(e))
        # Return empty chart with all days zeroed
        result = []
        for i in range(days):
            day = (datetime.now(UTC) - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            result.append({"date": day, "messages": 0})
        return result


@router.get("/popular-questions")
async def get_popular_questions(
    site_id: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Get most common user questions."""
    try:
        cutoff = datetime.now(UTC) - timedelta(days=90)
        sessions = await _load_sessions_capped(repos, site_id, cutoff)
        if not sessions:
            return []
        questions = []

        for s in sessions:
            messages = s.get("messages", [])
            for msg in messages:
                if msg.get("role") == "user":
                    content = msg.get("content", "").strip()
                    if content and len(content) > 5:
                        questions.append(content[:200])

        # Simple frequency count (could be improved with embedding clustering)
        counter = Counter(questions)
        return [{"question": q, "count": c} for q, c in counter.most_common(limit)]
    except Exception as e:
        logger.error("Analytics popular-questions error", error=str(e))
        return []


@router.get("/knowledge-gaps")
async def get_knowledge_gaps(
    site_id: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Find user questions where bot responses indicated no knowledge was found."""
    try:
        cutoff = datetime.now(UTC) - timedelta(days=90)
        sessions = await _load_sessions_capped(repos, site_id, cutoff)
        if not sessions:
            return []
        # Substrings that mark a "no knowledge" answer. These must cover the fallbacks
        # ChatAgent actually emits (_DEFAULT_NO_KNOWLEDGE_EN / _DEFAULT_NO_KNOWLEDGE_VI)
        # as well as free-form LLM phrasings, and stay broad enough to survive an
        # operator override of agent.no_knowledge_response_vi / _en in config.json.
        gap_indicators = [
            # English
            "i don't have",
            "i'm not sure",
            "i couldn't find",
            "no information",
            "i don't know",
            "sorry, i",
            "i apologize",
            # Vietnamese — "chưa có thông tin" is the default VI fallback's core phrase.
            "chưa có thông tin",
            "không có thông tin",
            "chưa có dữ liệu",
            "không có dữ liệu",
            "không tìm thấy",
            "chưa hỗ trợ",
            # First-person forms only. Bare "không biết" / "không rõ" / "xin lỗi" also
            # match advice aimed at the visitor ("nếu bạn không biết mã đơn hàng…") and
            # ordinary politeness, neither of which is a knowledge gap. Anchoring to the
            # pronoun mirrors the English "sorry, i". Both pronouns are listed because the
            # bot says "mình" or "tôi" depending on the configured fallback and prompt.
            "tôi không biết",
            "mình không biết",
            "tôi chưa biết",
            "mình chưa biết",
            "tôi không rõ",
            "mình không rõ",
            "xin lỗi, tôi",
            "xin lỗi, mình",
        ]
        gaps: list[str] = []

        for s in sessions:
            messages = s.get("messages", [])
            for i, msg in enumerate(messages):
                if msg.get("role") != "assistant":
                    continue
                content_lower = (msg.get("content") or "").lower()
                if any(indicator in content_lower for indicator in gap_indicators):
                    # Find the preceding user message
                    for j in range(i - 1, -1, -1):
                        if messages[j].get("role") == "user":
                            question = messages[j].get("content", "").strip()
                            if question and len(question) > 5:
                                gaps.append(question[:200])
                            break

        counter = Counter(gaps)
        return [{"question": q, "count": c} for q, c in counter.most_common(limit)]
    except Exception as e:
        logger.error("Analytics knowledge-gaps error", error=str(e))
        return []


@router.get("/tool-usage")
async def get_tool_usage(
    site_id: str = Query(...),
    days: int = Query(default=30, ge=1, le=365),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Get tool call statistics from chat sessions."""
    try:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        sessions = await _load_sessions_capped(repos, site_id, cutoff)
        tool_calls: Counter = Counter()
        tool_errors: Counter = Counter()

        for s in sessions:
            messages = s.get("messages", [])
            for msg in messages:
                if msg.get("role") != "assistant":
                    continue
                # Assistant messages persisted since the tool-analytics change carry a
                # "tool_calls" list of {"name", "success"} — one entry per executed tool.
                # Sessions stored before that (and turns with no tool use) simply have no
                # such key, which reads as "no tool data" rather than an error.
                for call in msg.get("tool_calls") or []:
                    if not isinstance(call, dict):
                        continue
                    name = call.get("name")
                    if not isinstance(name, str) or not name:
                        continue
                    tool_calls[name] += 1
                    if not call.get("success", False):
                        tool_errors[name] += 1

        tools = await repos.tools.list_by_site(site_id)
        result = []
        for tool in tools:
            name = tool.get("name", "unknown")
            result.append(
                {
                    "name": name,
                    "calls": tool_calls.get(name, 0),
                    "errors": tool_errors.get(name, 0),
                    "enabled": tool.get("enabled", True),
                }
            )
        return result
    except Exception as e:
        logger.error("Analytics tool-usage error", error=str(e))
        return []
