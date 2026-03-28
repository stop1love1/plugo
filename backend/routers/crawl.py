import json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from repositories import get_repos, create_repos, Repositories
from knowledge.crawler import WebCrawler
from auth import get_current_user, TokenData
from logging_config import logger

# Crawls running longer than this are considered stale and auto-failed
STALE_CRAWL_MINUTES = 30

router = APIRouter(prefix="/api/crawl", tags=["crawl"])

# Track running crawlers so we can stop them
_active_crawlers: dict[str, WebCrawler] = {}


async def cleanup_stale_crawls_on_startup():
    """Called on server startup to reset any 'running' crawls left from a previous process."""
    from repositories import create_repos
    repos = await create_repos()
    try:
        sites = await repos.sites.list_all()
        for site in sites:
            if site.get("crawl_status") == "running":
                site_id = site["id"]
                logger.warning("Resetting orphaned running crawl on startup", site_id=site_id, site_name=site.get("name"))
                await repos.sites.update(site_id, {"crawl_status": "idle"})
                # Fail any running jobs for this site
                jobs = await repos.crawl_jobs.list_by_site(site_id)
                for job in jobs:
                    if job.get("status") == "running":
                        await repos.crawl_jobs.update(job["id"], {
                            "status": "failed",
                            "error_log": "Auto-failed: server restarted while crawl was running",
                            "finished_at": datetime.now(timezone.utc),
                        })
    finally:
        await repos.close()


class CrawlToggleRequest(BaseModel):
    """Enable or disable crawling for a site."""
    enabled: bool
    auto_interval: Optional[int] = None   # Hours. 0 = disabled
    max_pages: Optional[int] = None


class CrawlStartRequest(BaseModel):
    """Trigger a manual crawl."""
    site_id: str
    url: Optional[str] = None             # If omitted, uses site.url
    max_pages: Optional[int] = None


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
    """
    Enable or disable crawling for a site.
    - Enable: starts crawling immediately if not already running.
    - Disable: stops active crawl (if any), retains all learned data in DB.
    """
    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    update_data = {"crawl_enabled": data.enabled}
    if data.auto_interval is not None:
        update_data["crawl_auto_interval"] = data.auto_interval
    if data.max_pages is not None:
        update_data["crawl_max_pages"] = data.max_pages

    if data.enabled:
        # === ENABLE CRAWL ===
        crawl_url = site["url"]
        if not crawl_url or not crawl_url.startswith(("http://", "https://")):
            # Save enabled state but warn about invalid URL
            update_data["crawl_status"] = "idle"
            await repos.sites.update(site_id, update_data)
            return {
                "message": f"Crawl enabled for {site['name']}, but site URL is invalid. Set a valid URL in Settings, then use Start Crawl.",
                "crawl_enabled": True,
                "crawl_status": "idle",
                "warning": "invalid_url",
            }

        update_data["crawl_status"] = "running"
        await repos.sites.update(site_id, update_data)

        max_pages = data.max_pages or site.get("crawl_max_pages", 50)

        job = await repos.crawl_jobs.create({
            "site_id": site_id,
            "start_url": crawl_url,
        })
        background_tasks.add_task(
            _run_crawl_with_tracking,
            site_id, crawl_url, job["id"], max_pages
        )

        return {
            "message": f"Crawl enabled for {site['name']}",
            "crawl_enabled": True,
            "crawl_status": "running",
            "job_id": job["id"],
        }
    else:
        # === DISABLE CRAWL ===
        # Stop crawler if running
        if site_id in _active_crawlers:
            _active_crawlers[site_id].stop()
            del _active_crawlers[site_id]

        update_data["crawl_status"] = "idle"
        site_updated = await repos.sites.update(site_id, update_data)

        return {
            "message": f"Crawl disabled for {site['name']}. Existing data retained ({site.get('knowledge_count', 0)} chunks).",
            "crawl_enabled": False,
            "crawl_status": "idle",
            "knowledge_count": site.get("knowledge_count", 0),
        }


# ============================================================
# 2. START CRAWL — Manual trigger (independent of toggle)
# ============================================================

async def _cleanup_stale_crawls(repos: Repositories, site_id: str) -> None:
    """Auto-fail crawl jobs that have been running longer than STALE_CRAWL_MINUTES."""
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_CRAWL_MINUTES)
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
                "error_log": f"Auto-failed: crawl exceeded {STALE_CRAWL_MINUTES} minute timeout",
                "finished_at": datetime.now(timezone.utc),
            })
    # If the site is still marked as "running" but has no active crawler, reset it
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

    # Clean up stale "running" jobs before checking status
    await _cleanup_stale_crawls(repos, data.site_id)
    # Re-fetch site after cleanup
    site = await repos.sites.get_by_id(data.site_id)

    if site.get("crawl_status") == "running":
        raise HTTPException(status_code=409, detail="Crawl already running. Stop it before starting a new one.")

    crawl_url = data.url or site["url"]
    max_pages = data.max_pages or site.get("crawl_max_pages", 50)

    await repos.sites.update(data.site_id, {"crawl_status": "running"})

    job = await repos.crawl_jobs.create({
        "site_id": data.site_id,
        "start_url": crawl_url,
    })

    background_tasks.add_task(
        _run_crawl_with_tracking,
        data.site_id, crawl_url, job["id"], max_pages,
    )

    return {
        "job_id": job["id"],
        "status": "started",
        "message": f"Crawling {crawl_url}",
    }


# ============================================================
# 3. STOP CRAWL — Stop a running crawl
# ============================================================

@router.post("/stop/{site_id}")
async def stop_crawl(
    site_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Stop a running crawl. Data already crawled is retained in the database."""
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
# 4. STATUS — Get current crawl status
# ============================================================

@router.get("/status/{site_id}")
async def get_crawl_status(
    site_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Get the current crawl status for a site."""
    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Auto-fix stale state: DB says "running" but no active crawler process
    if site.get("crawl_status") == "running" and site_id not in _active_crawlers:
        await _cleanup_stale_crawls(repos, site_id)
        site = await repos.sites.get_by_id(site_id)

    # Include live crawler info if running
    current_url = None
    crawler = _active_crawlers.get(site_id)
    if crawler:
        current_url = crawler.current_url

    return {
        "site_id": site_id,
        "crawl_enabled": site.get("crawl_enabled", False),
        "crawl_status": site.get("crawl_status", "idle"),
        "crawl_auto_interval": site.get("crawl_auto_interval", 0),
        "crawl_max_pages": site.get("crawl_max_pages", 50),
        "knowledge_count": site.get("knowledge_count", 0),
        "last_crawled_at": site.get("last_crawled_at"),
        "is_running": site_id in _active_crawlers,
        "current_url": current_url,
    }


# ============================================================
# 5. JOBS — Crawl history
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
    """Get structured crawl logs for a specific job."""
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
# 6. CLEAR KNOWLEDGE — Delete all learned data
# ============================================================

@router.delete("/knowledge/{site_id}")
async def clear_knowledge(
    site_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Delete all crawled knowledge for a site."""
    from agent.rag import rag_engine

    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Delete from vector store
    await rag_engine.delete_site(site_id)

    # Delete all chunks from database in bulk
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
# Background task helper
# ============================================================

async def _run_crawl_with_tracking(
    site_id: str,
    url: str,
    job_id: str,
    max_pages: int,
):
    """Background task: crawl + update site status when done. Supports continuous crawling."""
    repos = await create_repos()

    crawler = WebCrawler(max_pages=max_pages)
    _active_crawlers[site_id] = crawler

    try:
        await crawler.crawl_site(site_id, url, job_id, repos)

        # Update site stats
        knowledge_data = await repos.knowledge.list_by_site(site_id, page=1, per_page=1)
        total_chunks = knowledge_data.get("total", 0)

        await repos.sites.update(site_id, {
            "crawl_status": "idle",
            "last_crawled_at": datetime.now(timezone.utc),
            "knowledge_count": total_chunks,
        })

        # Continuous crawl: if enabled and crawler found more URLs than max_pages,
        # there are undiscovered pages — trigger another round
        site = await repos.sites.get_by_id(site_id)
        remaining_queue = crawler._queue_size
        if (
            site
            and site.get("crawl_enabled")
            and remaining_queue > 0
            and not crawler._stopped
            and crawler.chunks_created > 0  # Only continue if we actually learned something
        ):
            logger.info(
                "Continuous crawl: triggering next round",
                site_id=site_id,
                remaining_urls=remaining_queue,
            )
            next_job = await repos.crawl_jobs.create({
                "site_id": site_id,
                "start_url": url,
            })
            await repos.sites.update(site_id, {"crawl_status": "running"})
            _active_crawlers.pop(site_id, None)
            await repos.close()
            # Recursive call for next round
            await _run_crawl_with_tracking(site_id, url, next_job["id"], max_pages)
            return

    except Exception as e:
        logger.error("Crawl failed", site_id=site_id, job_id=job_id, error=str(e))
        await repos.sites.update(site_id, {"crawl_status": "idle"})
        await repos.crawl_jobs.update(job_id, {
            "status": "failed",
            "error_log": str(e),
            "finished_at": datetime.now(timezone.utc),
        })
    finally:
        _active_crawlers.pop(site_id, None)
        await repos.close()
