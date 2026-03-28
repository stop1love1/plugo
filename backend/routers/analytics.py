"""Analytics router — aggregate stats from chat sessions."""

from datetime import datetime, timedelta
from collections import Counter
from fastapi import APIRouter, Depends, Query
from repositories import get_repos, Repositories
from auth import get_current_user, TokenData

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview")
async def get_overview(
    site_id: str = Query(...),
    days: int = Query(default=30, ge=1, le=365),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Get overview stats: total sessions, messages, avg duration."""
    sessions = await repos.chat_sessions.list_by_site(site_id)
    cutoff = datetime.utcnow() - timedelta(days=days)

    total_sessions = 0
    total_messages = 0
    total_duration = 0
    sessions_with_duration = 0

    for s in sessions:
        started = s.get("started_at")
        if isinstance(started, str):
            started = datetime.fromisoformat(started)
        if started and started < cutoff:
            continue

        total_sessions += 1
        msg_count = s.get("message_count", len(s.get("messages", [])))
        total_messages += msg_count

        ended = s.get("ended_at")
        if started and ended:
            if isinstance(ended, str):
                ended = datetime.fromisoformat(ended)
            duration = (ended - started).total_seconds()
            if duration > 0:
                total_duration += duration
                sessions_with_duration += 1

    avg_duration = total_duration / sessions_with_duration if sessions_with_duration > 0 else 0
    avg_messages = total_messages / total_sessions if total_sessions > 0 else 0

    return {
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "avg_messages_per_session": round(avg_messages, 1),
        "avg_session_duration_seconds": round(avg_duration),
    }


@router.get("/messages-per-day")
async def get_messages_per_day(
    site_id: str = Query(...),
    days: int = Query(default=30, ge=1, le=365),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Get daily message counts for chart."""
    sessions = await repos.chat_sessions.list_by_site(site_id)
    cutoff = datetime.utcnow() - timedelta(days=days)
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
            if dt < cutoff:
                continue
            day = dt.strftime("%Y-%m-%d")
            daily_counts[day] = daily_counts.get(day, 0) + 1

    # Fill in missing days
    result = []
    for i in range(days):
        day = (datetime.utcnow() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        result.append({"date": day, "messages": daily_counts.get(day, 0)})

    return result


@router.get("/popular-questions")
async def get_popular_questions(
    site_id: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Get most common user questions."""
    sessions = await repos.chat_sessions.list_by_site(site_id)
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


@router.get("/knowledge-gaps")
async def get_knowledge_gaps(
    site_id: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Find user questions where bot responses indicated no knowledge was found."""
    sessions = await repos.chat_sessions.list_by_site(site_id)
    gap_indicators = [
        "i don't have", "i'm not sure", "i couldn't find", "no information",
        "không tìm thấy", "không có thông tin", "tôi không biết",
        "i don't know", "sorry, i", "i apologize",
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


@router.get("/tool-usage")
async def get_tool_usage(
    site_id: str = Query(...),
    days: int = Query(default=30, ge=1, le=365),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Get tool call statistics from chat sessions."""
    sessions = await repos.chat_sessions.list_by_site(site_id)
    cutoff = datetime.utcnow() - timedelta(days=days)
    tool_calls: Counter = Counter()
    tool_errors: Counter = Counter()

    for s in sessions:
        started = s.get("started_at")
        if isinstance(started, str):
            try:
                started = datetime.fromisoformat(started)
            except ValueError:
                started = None
        if started and started < cutoff:
            continue

        messages = s.get("messages", [])
        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", "")
            # Detect tool calls from response patterns
            if "tool_call" in str(msg) or "[Called " in content:
                tool_name = msg.get("tool_name", "unknown")
                tool_calls[tool_name] += 1
                if msg.get("tool_error"):
                    tool_errors[tool_name] += 1

    tools = await repos.tools.list_by_site(site_id)
    result = []
    for tool in tools:
        name = tool.get("name", "unknown")
        result.append({
            "name": name,
            "calls": tool_calls.get(name, 0),
            "errors": tool_errors.get(name, 0),
            "enabled": tool.get("enabled", True),
        })
    return result
