"""Auto-crawl scheduler — checks for sites needing re-crawl on a regular interval."""

import asyncio
import random
from datetime import datetime, timezone, timedelta
from config import settings
from logging_config import logger

_scheduler_task: asyncio.Task | None = None
JITTER_SECONDS = 30


async def _scheduler_loop():
    """Background loop that checks for sites needing auto-crawl."""
    from repositories import create_repos
    from routers.crawl import _active_crawlers, _run_crawl_with_tracking

    check_interval = settings.crawl_scheduler_interval
    max_concurrent = settings.crawl_max_concurrent_auto

    while True:
        try:
            jitter = random.uniform(0, JITTER_SECONDS)
            await asyncio.sleep(check_interval + jitter)

            repos = await create_repos()
            try:
                sites = await repos.sites.list_all()
                now = datetime.now(timezone.utc)

                running_count = len(_active_crawlers)

                for site in sites:
                    if running_count >= max_concurrent:
                        logger.debug(
                            "Auto-crawl concurrency limit reached",
                            running=running_count,
                            limit=max_concurrent,
                        )
                        break

                    site_id = site["id"]
                    enabled = site.get("crawl_enabled", False)
                    interval_hours = site.get("crawl_auto_interval", 0)

                    if not enabled or interval_hours <= 0:
                        continue

                    if site_id in _active_crawlers:
                        continue

                    # Check when last crawled
                    last_crawled = site.get("last_crawled_at")
                    if last_crawled:
                        if isinstance(last_crawled, str):
                            last_crawled = datetime.fromisoformat(last_crawled)
                        if not last_crawled.tzinfo:
                            last_crawled = last_crawled.replace(tzinfo=timezone.utc)
                        next_crawl_at = last_crawled + timedelta(hours=interval_hours)
                        if now < next_crawl_at:
                            continue

                    max_pages = site.get("crawl_max_pages", 50)
                    crawl_url = site["url"]

                    if not crawl_url or not crawl_url.startswith(("http://", "https://")):
                        logger.warning("Auto-crawl skipped: invalid URL", site_id=site_id, url=crawl_url)
                        continue

                    # Parse site-level crawl settings
                    max_depth = site.get("crawl_max_depth", 0)
                    exclude_raw = site.get("crawl_exclude_patterns", "")
                    exclude_patterns = [p.strip() for p in exclude_raw.split("\n") if p.strip()] if exclude_raw else []

                    job = await repos.crawl_jobs.create({
                        "site_id": site_id,
                        "start_url": crawl_url,
                    })
                    await repos.sites.update(site_id, {"crawl_status": "running"})

                    logger.info(
                        "Auto-crawl triggered",
                        site_id=site_id,
                        site_name=site.get("name"),
                        interval_hours=interval_hours,
                        job_id=job["id"],
                    )

                    asyncio.create_task(
                        _run_crawl_with_tracking(
                            site_id, crawl_url, job["id"], max_pages,
                            max_depth=max_depth,
                            exclude_patterns=exclude_patterns,
                        )
                    )
                    running_count += 1

            finally:
                await repos.close()

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Auto-crawl scheduler error", error=str(e))


def start_scheduler():
    """Start the auto-crawl scheduler as a background task."""
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_scheduler_loop())
        logger.info(
            "Auto-crawl scheduler started",
            check_interval=f"{settings.crawl_scheduler_interval}s",
            max_concurrent=settings.crawl_max_concurrent_auto,
        )


async def stop_scheduler():
    """Stop the auto-crawl scheduler."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        _scheduler_task = None
        logger.info("Auto-crawl scheduler stopped")
