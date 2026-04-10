import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from auth import TokenData, get_current_user
from config import settings
from knowledge.crawler import WebCrawler
from logging_config import logger
from repositories import Repositories, create_repos, get_repos

router = APIRouter(prefix="/api/crawl", tags=["crawl"])

# Track running crawlers so we can stop/pause them
_active_crawlers: dict[str, WebCrawler] = {}


async def cleanup_stale_crawls_on_startup():
    """Called on server startup to reset any 'running'/'paused' crawls left from a previous process."""
    from repositories import create_repos
    repos = await create_repos()
    try:
        sites = await repos.sites.list_all()
        for site in sites:
            if site.get("crawl_status") in ("running", "paused"):
                site_id = site["id"]
                logger.warning("Resetting orphaned crawl on startup", site_id=site_id, site_name=site.get("name"))
                await repos.sites.update(site_id, {"crawl_status": "idle"})
                jobs = await repos.crawl_jobs.list_by_site(site_id)
                for job in jobs:
                    if job.get("status") in ("running", "paused"):
                        await repos.crawl_jobs.update(job["id"], {
                            "status": "failed",
                            "error_log": "Auto-failed: server restarted while crawl was active",
                            "finished_at": datetime.now(UTC),
                        })
    finally:
        await repos.close()


# ============================================================
# Request models
# ============================================================

class CrawlToggleRequest(BaseModel):
    enabled: bool
    auto_interval: int | None = None
    max_pages: int | None = None
    max_depth: int | None = None
    exclude_patterns: str | None = None  # Newline-separated patterns


class CrawlStartRequest(BaseModel):
    site_id: str
    url: str | None = None
    max_pages: int | None = None
    max_depth: int | None = None
    force_recrawl: bool = False
    exclude_patterns: str | None = None


class CrawlSettingsRequest(BaseModel):
    """Update crawl settings without toggling or starting."""
    max_pages: int | None = None
    max_depth: int | None = None
    auto_interval: int | None = None
    exclude_patterns: str | None = None
    # Browser auth settings
    crawl_use_browser: bool | None = None
    crawl_login_url: str | None = None
    crawl_login_username_selector: str | None = None
    crawl_login_password_selector: str | None = None
    crawl_login_submit_selector: str | None = None
    crawl_login_username: str | None = None
    crawl_login_password: str | None = None
    crawl_login_success_url: str | None = None


def _parse_exclude_patterns(raw: str | None) -> list[str]:
    """Parse newline-separated exclude patterns string into a list."""
    if not raw:
        return []
    return [p.strip() for p in raw.split("\n") if p.strip()]


# ============================================================
# 1. TOGGLE CRAWL — Enable / Disable
# ============================================================

@router.put("/toggle/{site_id}")
async def toggle_crawl(
    site_id: str,
    data: CrawlToggleRequest,
    background_tasks: BackgroundTasks,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    update_data: dict = {"crawl_enabled": data.enabled}
    if data.auto_interval is not None:
        update_data["crawl_auto_interval"] = data.auto_interval
    if data.max_pages is not None:
        update_data["crawl_max_pages"] = data.max_pages
    if data.max_depth is not None:
        update_data["crawl_max_depth"] = data.max_depth
    if data.exclude_patterns is not None:
        update_data["crawl_exclude_patterns"] = data.exclude_patterns

    if data.enabled:
        crawl_url = site["url"]
        if not crawl_url or not crawl_url.startswith(("http://", "https://")):
            update_data["crawl_status"] = "idle"
            await repos.sites.update(site_id, update_data)
            return {
                "message": f"Crawl enabled for {site['name']}, but site URL is invalid.",
                "crawl_enabled": True,
                "crawl_status": "idle",
                "warning": "invalid_url",
            }

        update_data["crawl_status"] = "running"
        await repos.sites.update(site_id, update_data)

        max_pages = data.max_pages or site.get("crawl_max_pages", 50)
        max_depth = data.max_depth if data.max_depth is not None else site.get("crawl_max_depth", 0)
        exclude_raw = data.exclude_patterns if data.exclude_patterns is not None else site.get("crawl_exclude_patterns", "")

        job = await repos.crawl_jobs.create({
            "site_id": site_id,
            "start_url": crawl_url,
        })
        background_tasks.add_task(
            _run_crawl_with_tracking,
            site_id, crawl_url, job["id"], max_pages,
            max_depth=max_depth,
            exclude_patterns=_parse_exclude_patterns(exclude_raw),
            use_browser=site.get("crawl_use_browser", False),
        )

        return {
            "message": f"Crawl enabled for {site['name']}",
            "crawl_enabled": True,
            "crawl_status": "running",
            "job_id": job["id"],
        }
    else:
        if site_id in _active_crawlers:
            _active_crawlers[site_id].stop()
            del _active_crawlers[site_id]

        update_data["crawl_status"] = "idle"
        await repos.sites.update(site_id, update_data)

        return {
            "message": f"Crawl disabled for {site['name']}. Existing data retained ({site.get('knowledge_count', 0)} chunks).",
            "crawl_enabled": False,
            "crawl_status": "idle",
            "knowledge_count": site.get("knowledge_count", 0),
        }


# ============================================================
# 2. START CRAWL — Manual trigger
# ============================================================

async def _cleanup_stale_crawls(repos: Repositories, site_id: str) -> None:
    stale_minutes = settings.crawl_stale_timeout_minutes
    stale_cutoff = datetime.now(UTC) - timedelta(minutes=stale_minutes)
    jobs = await repos.crawl_jobs.list_by_site(site_id)
    for job in jobs:
        started = job.get("started_at")
        if isinstance(started, str):
            started = datetime.fromisoformat(started)
        if (
            job.get("status") == "running"
            and isinstance(started, datetime)
            and started < stale_cutoff
        ):
            logger.warning("Auto-failing stale crawl job", job_id=job["id"], site_id=site_id)
            await repos.crawl_jobs.update(job["id"], {
                "status": "failed",
                "error_log": f"Auto-failed: crawl exceeded {stale_minutes} minute timeout",
                "finished_at": datetime.now(UTC),
            })
    site = await repos.sites.get_by_id(site_id)
    if site and site.get("crawl_status") == "running" and site_id not in _active_crawlers:
        await repos.sites.update(site_id, {"crawl_status": "idle"})


@router.post("/start")
async def start_crawl(
    data: CrawlStartRequest,
    background_tasks: BackgroundTasks,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Trigger a manual crawl, regardless of crawl_enabled state."""
    site = await repos.sites.get_by_id(data.site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    await _cleanup_stale_crawls(repos, data.site_id)
    site = await repos.sites.get_by_id(data.site_id)

    if site.get("crawl_status") == "running":
        raise HTTPException(status_code=409, detail="Crawl already running. Stop it before starting a new one.")

    crawl_url = data.url or site["url"]
    max_pages = data.max_pages or site.get("crawl_max_pages", 50)
    max_depth = data.max_depth if data.max_depth is not None else site.get("crawl_max_depth", 0)
    exclude_raw = data.exclude_patterns if data.exclude_patterns is not None else site.get("crawl_exclude_patterns", "")

    await repos.sites.update(data.site_id, {"crawl_status": "running"})

    job = await repos.crawl_jobs.create({
        "site_id": data.site_id,
        "start_url": crawl_url,
    })

    background_tasks.add_task(
        _run_crawl_with_tracking,
        data.site_id, crawl_url, job["id"], max_pages,
        force_recrawl=data.force_recrawl,
        max_depth=max_depth,
        exclude_patterns=_parse_exclude_patterns(exclude_raw),
        use_browser=site.get("crawl_use_browser", False),
    )

    return {
        "job_id": job["id"],
        "status": "started",
        "message": f"Crawling {crawl_url}",
        "force_recrawl": data.force_recrawl,
    }


# ============================================================
# 3. STOP CRAWL
# ============================================================

@router.post("/stop/{site_id}")
async def stop_crawl(
    site_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    if site_id in _active_crawlers:
        _active_crawlers[site_id].stop()
        del _active_crawlers[site_id]

    await repos.sites.update(site_id, {"crawl_status": "idle"})

    return {
        "message": f"Crawl stopped. Retained {site.get('knowledge_count', 0)} existing chunks.",
        "crawl_status": "idle",
        "knowledge_count": site.get("knowledge_count", 0),
    }


# ============================================================
# 4. PAUSE / RESUME CRAWL
# ============================================================

@router.post("/pause/{site_id}")
async def pause_crawl(
    site_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Pause a running crawl. Can be resumed later."""
    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    crawler = _active_crawlers.get(site_id)
    if not crawler:
        raise HTTPException(status_code=409, detail="No active crawl to pause")

    crawler.pause()
    await repos.sites.update(site_id, {"crawl_status": "paused"})

    return {
        "message": f"Crawl paused for {site['name']}. Data collected so far is retained.",
        "crawl_status": "paused",
    }


@router.post("/resume/{site_id}")
async def resume_crawl(
    site_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Resume a paused crawl."""
    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    crawler = _active_crawlers.get(site_id)
    if not crawler:
        raise HTTPException(status_code=409, detail="No paused crawl to resume")

    crawler.resume()
    await repos.sites.update(site_id, {"crawl_status": "running"})

    return {
        "message": f"Crawl resumed for {site['name']}",
        "crawl_status": "running",
    }


# ============================================================
# 5. SETTINGS — Update crawl settings without toggling/starting
# ============================================================

@router.put("/settings/{site_id}")
async def update_crawl_settings(
    site_id: str,
    data: CrawlSettingsRequest,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Update crawl settings (max_pages, max_depth, auto_interval, exclude_patterns)."""
    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    update_data: dict = {}
    if data.max_pages is not None:
        update_data["crawl_max_pages"] = data.max_pages
    if data.max_depth is not None:
        update_data["crawl_max_depth"] = data.max_depth
    if data.auto_interval is not None:
        update_data["crawl_auto_interval"] = data.auto_interval
    if data.exclude_patterns is not None:
        update_data["crawl_exclude_patterns"] = data.exclude_patterns
    # Browser auth settings
    for field in (
        "crawl_use_browser", "crawl_login_url",
        "crawl_login_username_selector", "crawl_login_password_selector",
        "crawl_login_submit_selector", "crawl_login_username",
        "crawl_login_password", "crawl_login_success_url",
    ):
        val = getattr(data, field, None)
        if val is not None:
            # Don't overwrite password with the masked placeholder
            if field == "crawl_login_password" and val == "********":
                continue
            update_data[field] = val

    if not update_data:
        return {"message": "No settings to update"}

    await repos.sites.update(site_id, update_data)
    # Mask password in response to avoid echoing secrets
    safe_response = {**update_data}
    if "crawl_login_password" in safe_response and safe_response["crawl_login_password"]:
        safe_response["crawl_login_password"] = "********"
    return {"message": "Crawl settings updated", **safe_response}


# ============================================================
# 6. STATUS — Get current crawl status
# ============================================================

@router.get("/status/{site_id}")
async def get_crawl_status(
    site_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    if site.get("crawl_status") in ("running", "paused") and site_id not in _active_crawlers:
        await _cleanup_stale_crawls(repos, site_id)
        site = await repos.sites.get_by_id(site_id)

    current_url = None
    is_paused = False
    crawler = _active_crawlers.get(site_id)
    if crawler:
        current_url = crawler.current_url
        is_paused = crawler._paused

    return {
        "site_id": site_id,
        "crawl_enabled": site.get("crawl_enabled", False),
        "crawl_status": site.get("crawl_status", "idle"),
        "crawl_auto_interval": site.get("crawl_auto_interval", 0),
        "crawl_max_pages": site.get("crawl_max_pages", 50),
        "crawl_max_depth": site.get("crawl_max_depth", 0),
        "crawl_exclude_patterns": site.get("crawl_exclude_patterns", ""),
        "knowledge_count": site.get("knowledge_count", 0),
        "last_crawled_at": site.get("last_crawled_at"),
        "is_running": site_id in _active_crawlers,
        "is_paused": is_paused,
        "current_url": current_url,
        # Browser auth
        "crawl_use_browser": site.get("crawl_use_browser", False),
        "crawl_login_url": site.get("crawl_login_url", ""),
        "crawl_login_username_selector": site.get("crawl_login_username_selector", ""),
        "crawl_login_password_selector": site.get("crawl_login_password_selector", ""),
        "crawl_login_submit_selector": site.get("crawl_login_submit_selector", ""),
        "crawl_login_username": site.get("crawl_login_username", ""),
        "crawl_login_password": "********" if site.get("crawl_login_password") and site["crawl_login_password"] != "" else "",
        "crawl_login_success_url": site.get("crawl_login_success_url", ""),
    }


# ============================================================
# 7. JOBS — Crawl history
# ============================================================

@router.get("/jobs/{site_id}")
async def get_crawl_jobs(
    site_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    return await repos.crawl_jobs.list_by_site(site_id)


@router.get("/job/{job_id}/logs")
async def get_crawl_logs(
    job_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    job = await repos.crawl_jobs.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    logs = json.loads(job.get("crawl_log") or "[]")
    return {"logs": logs, "status": job.get("status"), "pages_done": job.get("pages_done", 0)}


@router.get("/job/{job_id}")
async def get_crawl_job(
    job_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    job = await repos.crawl_jobs.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")
    return job


# ============================================================
# 8. CLEAR KNOWLEDGE — Delete all learned data
# ============================================================

@router.delete("/knowledge/{site_id}")
async def clear_knowledge(
    site_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    from agent.rag import rag_engine

    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    await rag_engine.delete_site(site_id)

    data = await repos.knowledge.list_by_site(site_id, page=1, per_page=10000)
    chunk_ids = [chunk["id"] for chunk in data.get("chunks", [])]
    if chunk_ids:
        await repos.knowledge.delete_many(chunk_ids)

    await repos.sites.update(site_id, {"knowledge_count": 0})

    return {
        "message": f"All knowledge deleted for {site['name']}.",
        "knowledge_count": 0,
    }


# ============================================================
# 9. TEST BROWSER LOGIN
# ============================================================

@router.post("/test-login/{site_id}")
async def test_browser_login(
    site_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Test the browser login configuration for a site."""
    from knowledge.browser_crawler import PLAYWRIGHT_AVAILABLE, test_browser_login as _test_login

    if not PLAYWRIGHT_AVAILABLE:
        raise HTTPException(status_code=400, detail="Playwright is not installed on the server")

    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    if not site.get("crawl_login_url"):
        raise HTTPException(status_code=400, detail="Login URL not configured")
    if not site.get("crawl_login_username"):
        raise HTTPException(status_code=400, detail="Login credentials not configured")

    raw_password = await repos.sites.get_crawl_password(site_id)
    if not raw_password:
        raise HTTPException(status_code=400, detail="Login password not configured")

    result = await _test_login(
        login_url=site["crawl_login_url"],
        username=site["crawl_login_username"],
        password=raw_password,
        username_selector=site.get("crawl_login_username_selector", ""),
        password_selector=site.get("crawl_login_password_selector", ""),
        submit_selector=site.get("crawl_login_submit_selector", ""),
        success_url=site.get("crawl_login_success_url") or None,
    )
    return result


# ============================================================
# Background task helper
# ============================================================

async def _run_crawl_with_tracking(
    site_id: str,
    url: str,
    job_id: str,
    max_pages: int,
    force_recrawl: bool = False,
    max_depth: int = 0,
    exclude_patterns: list[str] | None = None,
    use_browser: bool = False,
):
    """Background task: crawl + update site status when done. Supports continuous crawling via iteration."""
    current_job_id = job_id
    round_number = 0
    max_rounds = settings.crawl_max_continuous_rounds

    # Browser login: extract cookies once before crawl loop
    auth_cookies = None
    if use_browser:
        try:
            from knowledge.browser_crawler import browser_login_and_extract_cookies
            repos_init = await create_repos()
            try:
                site = await repos_init.sites.get_by_id(site_id)
                if site and site.get("crawl_login_url") and site.get("crawl_login_username"):
                    raw_pw = await repos_init.sites.get_crawl_password(site_id)
                    auth_cookies = await browser_login_and_extract_cookies(
                        login_url=site["crawl_login_url"],
                        username=site["crawl_login_username"],
                        password=raw_pw or "",
                        username_selector=site.get("crawl_login_username_selector", ""),
                        password_selector=site.get("crawl_login_password_selector", ""),
                        submit_selector=site.get("crawl_login_submit_selector", ""),
                        success_url=site.get("crawl_login_success_url") or None,
                    )
                    logger.info("Browser login successful", site_id=site_id, cookies=len(auth_cookies))
            finally:
                await repos_init.close()
        except Exception as e:
            logger.error("Browser login failed, crawling without auth", site_id=site_id, error=str(e))

    while True:
        round_number += 1
        repos = await create_repos()
        crawler = WebCrawler(
            max_pages=max_pages,
            force_recrawl=force_recrawl,
            max_depth=max_depth,
            exclude_patterns=exclude_patterns,
            auth_cookies=auth_cookies,
        )
        _active_crawlers[site_id] = crawler

        try:
            await crawler.crawl_site(site_id, url, current_job_id, repos)

            knowledge_data = await repos.knowledge.list_by_site(site_id, page=1, per_page=1)
            total_chunks = knowledge_data.get("total", 0)

            await repos.sites.update(site_id, {
                "crawl_status": "idle",
                "last_crawled_at": datetime.now(UTC),
                "knowledge_count": total_chunks,
            })

            # Continuous crawl check
            site = await repos.sites.get_by_id(site_id)
            remaining_queue = crawler._queue_size
            if (
                site
                and site.get("crawl_enabled")
                and remaining_queue > 0
                and not crawler._stopped
                and not crawler._paused
                and crawler.chunks_created > 0
                and round_number < max_rounds
            ):
                logger.info(
                    "Continuous crawl: triggering next round",
                    site_id=site_id,
                    remaining_urls=remaining_queue,
                    round=round_number,
                    max_rounds=max_rounds,
                )
                next_job = await repos.crawl_jobs.create({
                    "site_id": site_id,
                    "start_url": url,
                })
                await repos.sites.update(site_id, {"crawl_status": "running"})
                _active_crawlers.pop(site_id, None)
                current_job_id = next_job["id"]
                # Don't force recrawl on subsequent rounds
                force_recrawl = False
                continue

            if round_number >= max_rounds and remaining_queue > 0:
                logger.info(
                    "Continuous crawl: max rounds reached",
                    site_id=site_id,
                    remaining_urls=remaining_queue,
                    rounds_completed=round_number,
                )

            break

        except Exception as e:
            logger.error("Crawl failed", site_id=site_id, job_id=current_job_id, error=str(e))
            await repos.sites.update(site_id, {"crawl_status": "idle"})
            await repos.crawl_jobs.update(current_job_id, {
                "status": "failed",
                "error_log": str(e),
                "finished_at": datetime.now(UTC),
            })
            break
        finally:
            _active_crawlers.pop(site_id, None)
            await repos.close()
