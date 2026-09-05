"""Background-crawl error paths must never crash the task that runs them.

`PRAGMA foreign_keys=ON` made a previously silent path raise: a `crawl_jobs.create`
for a site that was deleted mid-crawl now fails with `IntegrityError` instead of
writing an orphan row. That leaves the SQLAlchemy session in a pending-rollback
state, so the broad `except Exception` handler below the create — which does its own
status writes on that same session — used to raise a *second* exception that escaped
the background task entirely.

These tests provoke the real `IntegrityError` (the site row really is deleted, the FK
is really enforced) rather than injecting a fake one, so the pending-rollback state
that follows is real too. Only the *timing* of the delete is forced.
"""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, ClassVar

import pytest
from sqlalchemy.exc import IntegrityError

from repositories import Repositories, create_repos


class _LogRecorder:
    """Drop-in for the loguru `logger` that records what a module logged."""

    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, Any]]] = []

    def __getattr__(self, level: str) -> Callable[..., None]:
        def _log(message: str, **fields: Any) -> None:
            self.records.append((level, message, fields))

        return _log

    def messages(self, level: str | None = None) -> list[str]:
        return [message for lvl, message, _ in self.records if level is None or lvl == level]

    def fields_for(self, message: str) -> dict[str, Any]:
        for _lvl, recorded, fields in self.records:
            if recorded == message:
                return fields
        raise AssertionError(f"no log record for {message!r}; recorded: {self.messages()}")


def _make_crawler_class(queue_sizes: list[int], on_crawl: Callable[[], None] | None = None) -> type:
    """Build a `WebCrawler` stand-in that reports a scripted queue size per round.

    One entry of `queue_sizes` is consumed per constructed crawler, i.e. per
    continuous-crawl round; a non-zero size is what makes the loop start another round.
    """
    remaining = list(queue_sizes)

    class _FakeCrawler:
        calls: ClassVar[list[tuple[str, str, str]]] = []

        def __init__(self, **_kwargs: Any) -> None:
            self._queue_size = remaining.pop(0) if remaining else 0
            self._stopped = False
            self._paused = False
            self.chunks_created = 3

        async def crawl_site(self, site_id: str, url: str, job_id: str, repos: Repositories) -> None:
            _FakeCrawler.calls.append((site_id, url, job_id))
            if on_crawl is not None:
                on_crawl()

    return _FakeCrawler


async def _arm_deleted_site_race(monkeypatch: pytest.MonkeyPatch, queue_sizes: list[int]) -> dict[str, Any]:
    """Wire `routers.crawl` so the next `_run_crawl_with_tracking` hits the deleted-site race.

    The continuous-crawl loop reads the site, then creates the next round's job. The
    window between those two is a single await, so the only faithful way to land inside
    it is to delete the site as that read returns — which is what the `get_by_id`
    wrapper does, on the loop's own session, handing back the stale dict the loop
    already had in hand.

    Returns a state dict the test can assert on; `create_attempts` / `create_raised`
    prove the create was reached and what it raised.
    """
    import routers.crawl as crawl_module

    state: dict[str, Any] = {
        "crawled": False,
        "deleted": False,
        "create_attempts": [],
        "create_raised": [],
    }

    def _mark_crawled() -> None:
        state["crawled"] = True

    crawler_cls = _make_crawler_class(queue_sizes, on_crawl=_mark_crawled)
    state["crawler_calls"] = crawler_cls.calls

    async def _create_repos() -> Repositories:
        repos = await create_repos()
        real_get_by_id = repos.sites.get_by_id
        real_create = repos.crawl_jobs.create

        async def _get_by_id(site_id: str) -> dict | None:
            site = await real_get_by_id(site_id)
            if state["crawled"] and not state["deleted"]:
                state["deleted"] = True
                await repos.sites.delete(site_id)
            return site

        async def _create(data: dict) -> dict:
            state["create_attempts"].append(data)
            try:
                return await real_create(data)
            except Exception as exc:
                state["create_raised"].append(exc)
                raise

        repos.sites.get_by_id = _get_by_id
        repos.crawl_jobs.create = _create
        return repos

    monkeypatch.setattr(crawl_module, "WebCrawler", crawler_cls)
    monkeypatch.setattr(crawl_module, "create_repos", _create_repos)
    return state


@pytest.fixture
async def crawl_logs(monkeypatch: pytest.MonkeyPatch) -> _LogRecorder:
    """Capture what `routers.crawl` logs."""
    import routers.crawl as crawl_module

    recorder = _LogRecorder()
    monkeypatch.setattr(crawl_module, "logger", recorder)
    return recorder


# ---------------------------------------------------------------------------
# routers/crawl.py — the continuous-crawl round boundary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deleted_site_mid_crawl_does_not_crash_the_background_task(
    db_repos: Repositories,
    test_site: dict,
    monkeypatch: pytest.MonkeyPatch,
    crawl_logs: _LogRecorder,
) -> None:
    """A real FK IntegrityError on the next round's job must not escape the task."""
    from routers.crawl import _run_crawl_with_tracking

    site_id = test_site["id"]
    await db_repos.sites.update(site_id, {"crawl_enabled": True})
    job = await db_repos.crawl_jobs.create({"site_id": site_id, "start_url": test_site["url"]})

    state = await _arm_deleted_site_race(monkeypatch, queue_sizes=[7])

    # No pytest.raises wrapper: the point is that this returns at all.
    await _run_crawl_with_tracking(site_id, test_site["url"], job["id"], max_pages=5)

    # Prove the path was exercised rather than skipped: a round ran, the site really
    # was deleted, and the next round's create really did hit the foreign key.
    assert state["crawler_calls"] == [(site_id, test_site["url"], job["id"])]
    assert state["deleted"] is True
    assert len(state["create_attempts"]) == 1
    assert len(state["create_raised"]) == 1
    assert isinstance(state["create_raised"][0], IntegrityError)
    assert "FOREIGN KEY constraint failed" in str(state["create_raised"][0])

    # And the failure was logged rather than swallowed.
    assert "Crawl failed" in crawl_logs.messages("error")


@pytest.mark.asyncio
async def test_failed_status_writes_do_not_mask_the_original_crawl_error(
    db_repos: Repositories,
    test_site: dict,
    monkeypatch: pytest.MonkeyPatch,
    crawl_logs: _LogRecorder,
) -> None:
    """The handler's own writes fail here too; the original error must still be what is logged."""
    from routers.crawl import _run_crawl_with_tracking

    site_id = test_site["id"]
    await db_repos.sites.update(site_id, {"crawl_enabled": True})
    job = await db_repos.crawl_jobs.create({"site_id": site_id, "start_url": test_site["url"]})

    await _arm_deleted_site_race(monkeypatch, queue_sizes=[7])

    await _run_crawl_with_tracking(site_id, test_site["url"], job["id"], max_pages=5)

    errors = crawl_logs.messages("error")
    assert "Crawl failed" in errors
    # The original cause, not the follow-on session error, is what "Crawl failed" carries.
    assert "FOREIGN KEY constraint failed" in crawl_logs.fields_for("Crawl failed")["error"]

    # The guard was genuinely exercised: the handler's own status writes failed on the
    # pending-rollback session, and that second failure is reported separately and
    # *after* the original. If those writes had succeeded there would be no such
    # record, so this cannot pass for the wrong reason.
    assert "Crawl status update failed after crawl error" in errors
    assert errors.index("Crawl failed") < errors.index("Crawl status update failed after crawl error")
    followup = crawl_logs.fields_for("Crawl status update failed after crawl error")
    assert followup["site_id"] == site_id
    assert followup["job_id"] == job["id"]


@pytest.mark.asyncio
async def test_continuous_crawl_happy_path_still_creates_next_job_and_updates_status(
    db_repos: Repositories,
    test_site: dict,
    monkeypatch: pytest.MonkeyPatch,
    crawl_logs: _LogRecorder,
) -> None:
    """Nothing about the normal two-round path changes: next job created, site status written."""
    import routers.crawl as crawl_module
    from routers.crawl import _run_crawl_with_tracking

    site_id = test_site["id"]
    await db_repos.sites.update(site_id, {"crawl_enabled": True})
    job = await db_repos.crawl_jobs.create({"site_id": site_id, "start_url": test_site["url"]})

    crawler_cls = _make_crawler_class(queue_sizes=[4, 0])
    monkeypatch.setattr(crawl_module, "WebCrawler", crawler_cls)

    await _run_crawl_with_tracking(site_id, test_site["url"], job["id"], max_pages=5)

    assert crawl_logs.messages("error") == []

    verify = await create_repos()
    try:
        jobs = await verify.crawl_jobs.list_by_site(site_id)
        site = await verify.sites.get_by_id(site_id)
    finally:
        await verify.close()

    assert len(jobs) == 2, "round one must create the next round's job"
    next_job_id = next(j["id"] for j in jobs if j["id"] != job["id"])
    # Two rounds ran, the second against the job the first round created.
    assert crawler_cls.calls == [
        (site_id, test_site["url"], job["id"]),
        (site_id, test_site["url"], next_job_id),
    ]
    assert site is not None
    assert site["crawl_status"] == "idle"
    assert site["last_crawled_at"] is not None


# ---------------------------------------------------------------------------
# scheduler.py — the auto-crawl tick
# ---------------------------------------------------------------------------


class _FakeAsyncio:
    """Stands in for `scheduler.asyncio` so a tick runs with no real delay.

    The first sleep returns immediately, the second raises `CancelledError`, which the
    loop already treats as "stop" — so `_scheduler_loop()` runs exactly one tick and
    then returns.
    """

    CancelledError = asyncio.CancelledError

    def __init__(self) -> None:
        self.sleeps = 0
        self.tasks: list[asyncio.Task] = []

    async def sleep(self, _delay: float) -> None:
        self.sleeps += 1
        if self.sleeps > 1:
            raise asyncio.CancelledError

    def create_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        task = asyncio.ensure_future(coro)
        self.tasks.append(task)
        return task


async def _make_site_due_for_auto_crawl(db_repos: Repositories, site: dict) -> None:
    """Make `site` due for an auto-crawl on the next scheduler tick."""
    await db_repos.sites.update(
        site["id"],
        {"crawl_enabled": True, "crawl_auto_interval": 1, "crawl_status": "idle"},
    )


@pytest.fixture
async def scheduler_harness(monkeypatch: pytest.MonkeyPatch) -> tuple[_FakeAsyncio, _LogRecorder, list[str]]:
    """Patch scheduler.py so one tick runs immediately and spawns no real crawls."""
    import routers.crawl as crawl_module
    import scheduler as scheduler_module

    fake_asyncio = _FakeAsyncio()
    recorder = _LogRecorder()
    started: list[str] = []

    async def _fake_run_crawl(site_id: str, *_args: Any, **_kwargs: Any) -> None:
        started.append(site_id)

    monkeypatch.setattr(scheduler_module, "asyncio", fake_asyncio)
    monkeypatch.setattr(scheduler_module, "logger", recorder)
    monkeypatch.setattr(crawl_module, "_run_crawl_with_tracking", _fake_run_crawl)
    return fake_asyncio, recorder, started


@pytest.mark.asyncio
async def test_scheduler_tick_survives_a_site_deleted_before_its_job_is_created(
    db_repos: Repositories,
    test_site: dict,
    monkeypatch: pytest.MonkeyPatch,
    scheduler_harness: tuple[_FakeAsyncio, _LogRecorder, list[str]],
) -> None:
    """The tick's job-creation failure must be handled where it happens, not by the catch-all."""
    import repositories as repositories_module
    import scheduler as scheduler_module

    fake_asyncio, recorder, started = scheduler_harness
    site_id = test_site["id"]
    await _make_site_due_for_auto_crawl(db_repos, test_site)

    attempts: list[dict] = []
    raised: list[Exception] = []

    async def _patched_create_repos() -> Repositories:
        repos = await create_repos()
        real_list_all = repos.sites.list_all
        real_create = repos.crawl_jobs.create

        async def _list_all() -> list[dict]:
            sites = await real_list_all()
            # The scheduler's window is wide: it lists sites once per tick and creates
            # their jobs later. Deleting here leaves the target site in the tick's list
            # with its row already gone — the real race, on the tick's own session.
            await repos.sites.delete(site_id)
            return sites

        async def _create(data: dict) -> dict:
            attempts.append(data)
            try:
                return await real_create(data)
            except Exception as exc:
                raised.append(exc)
                raise

        repos.sites.list_all = _list_all
        repos.crawl_jobs.create = _create
        return repos

    monkeypatch.setattr(repositories_module, "create_repos", _patched_create_repos)

    await scheduler_module._scheduler_loop()

    # The tick really ran and really hit the FK violation.
    assert fake_asyncio.sleeps == 2
    assert [attempt["site_id"] for attempt in attempts] == [site_id]
    assert len(raised) == 1
    assert isinstance(raised[0], IntegrityError)
    assert "FOREIGN KEY constraint failed" in str(raised[0])

    # Handled at the point of failure, with the site named...
    messages = recorder.messages("error")
    assert "Auto-crawl job creation failed" in messages
    assert recorder.fields_for("Auto-crawl job creation failed")["site_id"] == site_id
    # ...and not by the loop's catch-all, which is where it landed before.
    assert "Auto-crawl scheduler error" not in messages
    assert started == []


@pytest.mark.asyncio
async def test_scheduler_tick_still_schedules_an_eligible_site(
    db_repos: Repositories,
    test_site: dict,
    scheduler_harness: tuple[_FakeAsyncio, _LogRecorder, list[str]],
) -> None:
    """Happy path: an eligible site still gets a job row, a status flip and a crawl task."""
    import scheduler as scheduler_module

    fake_asyncio, recorder, started = scheduler_harness
    site_id = test_site["id"]
    await _make_site_due_for_auto_crawl(db_repos, test_site)

    await scheduler_module._scheduler_loop()

    if fake_asyncio.tasks:
        await asyncio.gather(*fake_asyncio.tasks)

    assert site_id in started
    assert "Auto-crawl scheduler error" not in recorder.messages("error")

    verify = await create_repos()
    try:
        jobs = await verify.crawl_jobs.list_by_site(site_id)
        site = await verify.sites.get_by_id(site_id)
    finally:
        await verify.close()

    assert len(jobs) == 1
    assert site is not None
    assert site["crawl_status"] == "running"
