"""Summarization must actually reduce the context sent to the LLM.

`ConversationSummarizer` exists to cut token usage, but a summary only helps if the
history it covers stops being replayed verbatim. These tests pin the three things that
makes true:

* a live WebSocket session drops the summarized prefix from `agent.messages`;
* a resumed session with a summary replays only the tail the summary leaves out;
* the persisted session record still holds everything, and no trim boundary can
  separate a tool result from the tool call it answers, in any provider shape.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from fastapi import WebSocketDisconnect

from agent.core import ChatAgent
from agent.memory import ConversationSummarizer, trim_messages_for_context
from repositories import Repositories, create_repos

KEEP = ConversationSummarizer.KEEP_RECENT_MESSAGES
SUMMARY_TEXT = "The visitor asked about shipping and was told it takes three days."


class _StubProvider:
    """LLM stub for both the chat agent and the summarizer."""

    supports_tools = False

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.last_usage: dict | None = None

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> dict:
        return {"content": SUMMARY_TEXT, "tool_calls": [], "usage": None}

    async def stream(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        yield "Sure thing."


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """No real providers: the agent, the summarizer and the memory extractor all stub out."""
    monkeypatch.setattr("agent.core.get_llm_provider", lambda *a, **k: _StubProvider())
    monkeypatch.setattr("routers.chat.get_llm_provider", lambda *a, **k: _StubProvider())


def _make_agent(llm_provider: str = "claude") -> ChatAgent:
    return ChatAgent(
        site_id="site-1",
        site_name="Test Site",
        site_url="https://example.com",
        llm_provider=llm_provider,
        llm_model="test-model",
    )


def _persisted_history(turns: int) -> list[dict]:
    """A stored session's message list: alternating visitor/assistant turns."""
    history: list[dict] = []
    for i in range(turns):
        history.append({"role": "user", "content": f"question {i}", "timestamp": "2026-01-01T00:00:00Z"})
        history.append({"role": "assistant", "content": f"answer {i}", "timestamp": "2026-01-01T00:00:01Z"})
    return history


def _background_task_baseline() -> set[asyncio.Task]:
    """Snapshot `routers.chat._background_tasks` so a drain can ignore foreign tasks."""
    from routers.chat import _background_tasks

    return set(_background_tasks)


async def _drain_background_tasks(baseline: set[asyncio.Task], timeout: float = 10.0) -> None:
    """Await the `_fire_and_forget` tasks started since `baseline` — the summarizer is one.

    `_background_tasks` is a module global whose entries are only discarded by a done
    callback, so a task another test left behind on a now-closed loop would never clear.
    Waiting on the whole set would hang until the deadline on every call; waiting only on
    what this test started keeps that state out of the picture. A task of ours that really
    does overrun the deadline is a failure, not something to proceed past silently.
    """
    from routers.chat import _background_tasks

    pending = [task for task in _background_tasks if task not in baseline]
    if not pending:
        return
    _, still_running = await asyncio.wait(pending, timeout=timeout)
    if still_running:
        raise AssertionError(f"background tasks still running after {timeout}s: {still_running}")


class _FakeWebSocket:
    """Feeds `_run_websocket_chat` a scripted frame sequence, then disconnects."""

    def __init__(self, frames: list[dict], on_receive: Callable[[], Awaitable[None]] | None = None) -> None:
        self.headers: dict[str, str] = {}
        self.sent: list[dict] = []
        self.closed: list[tuple[int, str]] = []
        self._frames = list(frames)
        self._on_receive = on_receive

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)

    async def receive_json(self) -> dict:
        if self._on_receive is not None:
            await self._on_receive()
        if not self._frames:
            raise WebSocketDisconnect(code=1000)
        return self._frames.pop(0)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed.append((code, reason))


# --- Trim primitive: shape integrity across every provider format -------------------


def _build_tool_history(llm_provider: str, turns: int, tool_turn: int) -> list[dict]:
    """A conversation whose `tool_turn`-th turn ran a tool, in `llm_provider`'s own shape.

    Built by calling the production writer so the fixtures can't drift from it.
    """
    agent = _make_agent(llm_provider)
    for i in range(turns):
        agent.messages.append({"role": "user", "content": f"question {i}"})
        if i == tool_turn:
            agent._append_tool_messages(
                {"id": f"call-{i}", "name": "lookup_order", "arguments": {"order_id": str(i)}},
                '{"success": true}',
            )
        agent.messages.append({"role": "assistant", "content": f"answer {i}"})
    return agent.messages


def _assert_provider_valid(messages: list[dict]) -> None:
    """Assert `messages` is a conversation a provider API would accept."""
    assert messages, "trimming must never empty the conversation"
    assert messages[0]["role"] == "user", f"conversation opens on a {messages[0]['role']} message"
    seen_call_ids: set[str] = set()
    for msg in messages:
        for call in msg.get("tool_calls") or []:
            seen_call_ids.add(call["id"])
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_use":
                    seen_call_ids.add(block["id"])
                elif block.get("type") == "tool_result":
                    assert block["tool_use_id"] in seen_call_ids, "tool_result kept without its tool_use"
        if msg.get("role") == "tool":
            assert msg["tool_call_id"] in seen_call_ids, "tool message kept without its tool call"


@pytest.mark.parametrize("llm_provider", ["claude", "openai", "gemini"])
def test_trim_never_orphans_a_tool_result(llm_provider: str) -> None:
    """No cut point, in any provider shape, may strand a tool result or open on an
    assistant message — either makes the provider reject the whole conversation."""
    history = _build_tool_history(llm_provider, turns=5, tool_turn=2)
    for keep_recent in range(1, len(history) + 1):
        trimmed = trim_messages_for_context(history, keep_recent)
        _assert_provider_valid(trimmed)
        assert trimmed == history[len(history) - len(trimmed) :], "trim must keep a contiguous tail"


@pytest.mark.parametrize("llm_provider", ["claude", "openai", "gemini"])
def test_trim_actually_drops_older_messages(llm_provider: str) -> None:
    """Guards the test above against passing by simply never trimming anything."""
    history = _build_tool_history(llm_provider, turns=5, tool_turn=2)
    trimmed = trim_messages_for_context(history, KEEP)
    assert len(trimmed) < len(history)
    assert {"role": "user", "content": "question 0"} not in trimmed
    assert history[-1] in trimmed


def test_persisted_tool_call_records_count_as_ordinary_turns() -> None:
    """A stored assistant message carries the analytics record `{"name", "success"}`
    under the same `tool_calls` key the OpenAI wire format uses. It is still an ordinary
    assistant turn, and must count towards the retained tail."""
    history = _persisted_history(6)
    for msg in history:
        if msg["role"] == "assistant":
            msg["tool_calls"] = [{"name": "lookup_order", "success": True}]

    trimmed = trim_messages_for_context(history, KEEP)

    assert len(trimmed) == KEEP
    assert trimmed == history[-KEEP:]


def test_trim_declines_when_no_turn_start_precedes_the_cut() -> None:
    """With no plain visitor message to cut at, the walk back reaches index 0 and nothing
    is trimmed. Keeping more than intended is the only safe outcome — every alternative
    orphans a tool result or opens the conversation on an assistant message — and it must
    not run off the front of the list."""
    agent = _make_agent()
    tool_only = [
        msg
        for i in range(5)
        for msg in (
            {"role": "assistant", "content": [{"type": "tool_use", "id": f"c{i}", "name": "t", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"c{i}", "content": "{}"}]},
        )
    ]
    assistant_only = [{"role": "assistant", "content": f"answer {i}"} for i in range(10)]

    for history in (tool_only, assistant_only):
        assert trim_messages_for_context(history, 1) == history
        assert trim_messages_for_context(history, KEEP) == history
        agent.messages[:] = history
        assert agent.summary_boundary(KEEP) is None


def test_trim_leaves_short_conversations_alone() -> None:
    history = _persisted_history(2)
    assert trim_messages_for_context(history, KEEP) == history


def test_trim_does_not_mutate_its_input() -> None:
    history = _persisted_history(12)
    original = [dict(msg) for msg in history]
    trim_messages_for_context(history, KEEP)
    assert history == original


# --- Live session: summarization shrinks the LLM-facing history ---------------------


@pytest.mark.asyncio
async def test_summarization_trims_live_agent_history(db_repos: Repositories, test_site: dict) -> None:
    """After the background summarizer lands, the agent stops carrying what it covers —
    while the persisted session record keeps every message."""
    from routers.chat import _maybe_summarize

    session = await db_repos.chat_sessions.create({"site_id": test_site["id"]})
    persisted = _persisted_history(12)  # 24 messages, past MESSAGE_THRESHOLD
    await db_repos.chat_sessions.update_messages(session["id"], persisted)

    agent = _make_agent()
    for msg in persisted:
        agent.messages.append({"role": msg["role"], "content": msg["content"]})

    await _maybe_summarize(session["id"], test_site, list(persisted), agent, agent.summary_boundary(KEEP))

    assert agent.apply_staged_summary() == SUMMARY_TEXT
    assert len(agent.messages) == KEEP
    assert agent.messages == [{"role": m["role"], "content": m["content"]} for m in persisted[-KEEP:]]
    assert all(msg["content"] != "question 0" for msg in agent.messages)

    stored = await db_repos.chat_sessions.get_by_id(session["id"])
    assert len(stored["messages"]) == len(persisted)
    assert stored["messages"][0]["content"] == "question 0"


@pytest.mark.asyncio
async def test_messages_arriving_after_the_snapshot_are_never_dropped(db_repos: Repositories, test_site: dict) -> None:
    """A boundary pinned at dispatch keeps everything appended after it, whenever the pass
    that owns it finishes.

    Deterministic rather than interleaved: `asyncio.create_task` doesn't start the
    coroutine until the next await point, so the late turns land before the summarizer
    runs at all. That ordering is the point — the boundary has to hold regardless of when
    the pass completes. The genuinely concurrent path, where the summarizer really does
    run while the socket takes messages, is covered by
    `test_websocket_session_trims_context_once_summarized`.
    """
    from routers.chat import _maybe_summarize

    session = await db_repos.chat_sessions.create({"site_id": test_site["id"]})
    persisted = _persisted_history(12)
    agent = _make_agent()
    for msg in persisted:
        agent.messages.append({"role": msg["role"], "content": msg["content"]})

    summarize = asyncio.create_task(
        _maybe_summarize(session["id"], test_site, list(persisted), agent, agent.summary_boundary(KEEP))
    )

    # Two more turns land after the snapshot was taken.
    late_turns = [
        {"role": "user", "content": "late question"},
        {"role": "assistant", "content": "late answer"},
        {"role": "user", "content": "later question"},
        {"role": "assistant", "content": "later answer"},
    ]
    agent.messages.extend(late_turns)
    await summarize

    assert agent.apply_staged_summary() == SUMMARY_TEXT
    assert agent.messages[-len(late_turns) :] == late_turns
    assert len(agent.messages) == KEEP + len(late_turns)


@pytest.mark.asyncio
async def test_websocket_session_trims_context_once_summarized(
    db_repos: Repositories, test_site: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end through the WebSocket turn loop: at the summarization threshold the
    prompt swaps the older history for the summary instead of carrying both.

    The threshold lands on turn 20 — the loop dispatches the summarizer every 20 stored
    messages and `should_summarize` needs strictly more than `MESSAGE_THRESHOLD`, so the
    first pass that writes anything is the one snapshotting 40 messages.
    """
    from routers.chat import _run_websocket_chat, _ws_rate_limiter

    # 21 turns exceeds the per-session WS message cap, which isn't what's under test.
    monkeypatch.setattr(_ws_rate_limiter, "is_allowed", lambda session_id, site_token: True)

    turns: list[dict] = []

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
        turns.append({"history_len": len(self.messages), "summary": conversation_summary})
        return "system prompt", [], True

    monkeypatch.setattr(ChatAgent, "_build_system_prompt", _fake_build_system_prompt)

    baseline = _background_task_baseline()

    async def _drain() -> None:
        await _drain_background_tasks(baseline)

    site = {**test_site, "is_approved": True}
    websocket = _FakeWebSocket(
        frames=[{"message": f"question {i}"} for i in range(21)],
        on_receive=_drain,
    )
    ws_repos = await create_repos()
    await _run_websocket_chat(
        websocket,
        ws_repos,
        site,
        site["token"],
        first_data={"type": "init", "visitor_id": "visitor-1"},
    )
    await _drain_background_tasks(baseline)

    assert len(turns) == 21
    # Turn 20 closes the window that triggers summarization and still sees everything;
    # turn 21 is the first to run with the summary, and must no longer carry the history
    # the summary replaces.
    assert turns[19]["summary"] is None
    assert turns[19]["history_len"] == 39
    assert turns[20]["summary"] == SUMMARY_TEXT
    assert turns[20]["history_len"] == KEEP + 1  # the retained tail plus the new question

    connected = websocket.sent[0]
    stored = await db_repos.chat_sessions.get_by_id(connected["session_id"])
    assert len(stored["messages"]) == 42
    assert stored["messages"][0]["content"] == "question 0"


# --- Resumed session: the replay is bounded the same way ----------------------------


async def _resume_and_capture_agent(site: dict, session_id: str) -> tuple[list[dict], list[dict]]:
    """Resume `session_id` over a fake socket; return (agent messages, connected frame history)."""
    from routers.chat import _run_websocket_chat, active_agents

    captured: list[dict] = []

    async def _capture() -> None:
        agent = active_agents.get(session_id)
        if agent is not None:
            captured.extend(agent.messages)

    baseline = _background_task_baseline()
    websocket = _FakeWebSocket(frames=[], on_receive=_capture)
    ws_repos = await create_repos()
    await _run_websocket_chat(
        websocket,
        ws_repos,
        site,
        site["token"],
        first_data={"type": "init", "session_id": session_id, "visitor_id": "visitor-1"},
    )
    await _drain_background_tasks(baseline)
    return captured, websocket.sent[0]["history"]


@pytest.mark.asyncio
async def test_resume_with_summary_replays_only_the_uncovered_tail(db_repos: Repositories, test_site: dict) -> None:
    session = await db_repos.chat_sessions.create({"site_id": test_site["id"]})
    persisted = _persisted_history(12)
    await db_repos.chat_sessions.update_messages(session["id"], persisted)
    await db_repos.conversation_summaries.upsert_by_session(
        session_id=session["id"],
        data={
            "site_id": test_site["id"],
            "summary_text": SUMMARY_TEXT,
            "message_count_summarized": len(persisted) - KEEP,
            "total_message_count": len(persisted),
        },
    )

    agent_messages, sent_history = await _resume_and_capture_agent({**test_site, "is_approved": True}, session["id"])

    assert len(agent_messages) == KEEP
    assert agent_messages == [{"role": m["role"], "content": m["content"]} for m in persisted[-KEEP:]]
    # The widget and the persisted record still see the whole conversation.
    assert len(sent_history) == len(persisted)
    stored = await db_repos.chat_sessions.get_by_id(session["id"])
    assert len(stored["messages"]) == len(persisted)


@pytest.mark.asyncio
async def test_resume_keeps_messages_the_summary_never_covered(db_repos: Repositories, test_site: dict) -> None:
    """A summary only reaches as far as the pass that wrote it got.

    Summarization fires every 20 stored messages, so a session can close with up to 19
    more than the last pass took in. Trimming to a fixed recent tail would drop those —
    they are in neither the summary nor the replayed history, and nothing else records
    them for the model. The row's `message_count_summarized` says where the summary
    actually stops, so the replay starts there.
    """
    session = await db_repos.chat_sessions.create({"site_id": test_site["id"]})
    persisted = _persisted_history(29)  # 58 messages; the last pass ran at 40
    covered = 40 - KEEP  # what that pass summarized
    await db_repos.chat_sessions.update_messages(session["id"], persisted)
    await db_repos.conversation_summaries.upsert_by_session(
        session_id=session["id"],
        data={
            "site_id": test_site["id"],
            "summary_text": SUMMARY_TEXT,
            "message_count_summarized": covered,
            "total_message_count": 40,
        },
    )

    agent_messages, _ = await _resume_and_capture_agent({**test_site, "is_approved": True}, session["id"])

    assert len(agent_messages) == len(persisted) - covered
    assert agent_messages == [{"role": m["role"], "content": m["content"]} for m in persisted[covered:]]


@pytest.mark.asyncio
async def test_resume_without_summary_replays_everything(db_repos: Repositories, test_site: dict) -> None:
    """Nothing summarizes the older turns yet, so dropping them would just lose context."""
    session = await db_repos.chat_sessions.create({"site_id": test_site["id"]})
    persisted = _persisted_history(12)
    await db_repos.chat_sessions.update_messages(session["id"], persisted)

    agent_messages, _ = await _resume_and_capture_agent({**test_site, "is_approved": True}, session["id"])

    assert len(agent_messages) == len(persisted)


def test_replay_tolerates_a_stored_message_missing_its_content() -> None:
    """A malformed stored row replays as empty rather than aborting the visitor's turn.

    Both transports write `role` and `content` on every message, so this is defence in
    depth — but it is defence the SSE path had before it moved onto this shared helper,
    and a `KeyError` here would surface as a failed chat mid-request.
    """
    from routers.chat import restore_agent_history

    agent = _make_agent()
    restore_agent_history(
        agent,
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant"},
            {"content": "orphaned content"},
        ],
        None,
    )

    assert agent.messages == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": ""},
        {"role": "assistant", "content": "orphaned content"},
    ]


def test_a_slow_summarizer_cannot_trim_past_what_it_covers() -> None:
    """A summarizer slower than the twenty messages between passes leaves two passes in
    flight. Each carries its own boundary, so whichever lands trims to exactly what it
    covers rather than to the other pass's reach."""
    agent = _make_agent()
    agent.messages.extend([{"role": m["role"], "content": m["content"]} for m in _persisted_history(12)])

    first_boundary = agent.summary_boundary(KEEP)  # first pass dispatched; still running
    agent.messages.extend([{"role": m["role"], "content": m["content"]} for m in _persisted_history(6)])
    second_boundary = agent.summary_boundary(KEEP)  # second pass dispatched before it landed
    assert first_boundary is not second_boundary

    agent.stage_summary(SUMMARY_TEXT, first_boundary)  # ...and the first pass finishes first
    assert agent.apply_staged_summary() == SUMMARY_TEXT
    assert agent.messages[0] is first_boundary
    assert len(agent.messages) == KEEP + 12


def test_a_summary_overtaken_by_a_later_pass_is_discarded() -> None:
    """Out-of-order completion: a later pass already trimmed past this one's boundary, so
    this summary covers less than the history that survived it. Applying its text anyway
    would pair a broad tail with a narrow summary, so the whole pair is dropped."""
    agent = _make_agent()
    agent.messages.extend([{"role": m["role"], "content": m["content"]} for m in _persisted_history(12)])
    overtaken_boundary = agent.summary_boundary(KEEP)  # pass A dispatched
    agent.messages.extend([{"role": m["role"], "content": m["content"]} for m in _persisted_history(6)])

    # Pass B is dispatched later, finishes first, and trims past A's boundary.
    agent.stage_summary("a broader summary", agent.summary_boundary(KEEP))
    assert agent.apply_staged_summary() == "a broader summary"
    assert all(msg is not overtaken_boundary for msg in agent.messages)

    # Pass A finishes afterwards. Its summary no longer describes what is left.
    surviving_history = list(agent.messages)
    agent.stage_summary(SUMMARY_TEXT, overtaken_boundary)
    assert agent.apply_staged_summary() is None
    assert agent.messages == surviving_history


# --- Task 4 interaction: per-turn tool recording is untouched by trimming ------------


def test_trimming_does_not_disturb_recorded_tool_calls() -> None:
    """Tool-usage analytics reads the per-turn `last_tool_calls` accumulator, not the
    message list, which is exactly why trimming the message list can't break it."""
    agent = _make_agent()
    agent.messages.extend(_build_tool_history("claude", turns=5, tool_turn=2))
    agent._record_tool_call("lookup_order", {"success": True})

    agent.stage_summary(SUMMARY_TEXT, agent.summary_boundary(KEEP))
    assert agent.apply_staged_summary() == SUMMARY_TEXT

    assert agent.messages[0] == {"role": "user", "content": "question 2"}, "history was not trimmed"
    assert agent.last_tool_calls == [{"name": "lookup_order", "success": True}]
