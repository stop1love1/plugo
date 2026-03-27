from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from repositories import get_repos, Repositories
from knowledge.crawler import WebCrawler

router = APIRouter(prefix="/api/crawl", tags=["crawl"])

# Track running crawlers so we can stop them
_active_crawlers: dict[str, WebCrawler] = {}


class CrawlToggleRequest(BaseModel):
    """Bật/tắt crawl cho site."""
    enabled: bool
    auto_interval: Optional[int] = None   # Giờ. 0 = không tự động
    max_pages: Optional[int] = None


class CrawlStartRequest(BaseModel):
    """Trigger crawl thủ công."""
    site_id: str
    url: Optional[str] = None             # Nếu không truyền, dùng site.url
    max_pages: Optional[int] = None


# ============================================================
# 1. TOGGLE CRAWL — Bật/Tắt
# ============================================================

@router.put("/toggle/{site_id}")
async def toggle_crawl(
    site_id: str,
    data: CrawlToggleRequest,
    background_tasks: BackgroundTasks,
    repos: Repositories = Depends(get_repos),
):
    """
    Bật/tắt crawl cho site.
    - Bật: bắt đầu crawl ngay nếu chưa chạy, lưu trạng thái.
    - Tắt: dừng crawl đang chạy (nếu có), giữ lại data đã học trong DB.
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
        # === BẬT CRAWL ===
        update_data["crawl_status"] = "running"
        await repos.sites.update(site_id, update_data)

        # Start crawl in background
        crawl_url = site["url"]
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
            "message": f"Crawl đã BẬT cho {site['name']}",
            "crawl_enabled": True,
            "crawl_status": "running",
            "job_id": job["id"],
        }
    else:
        # === TẮT CRAWL ===
        # Stop crawler if running
        if site_id in _active_crawlers:
            _active_crawlers[site_id].stop()
            del _active_crawlers[site_id]

        update_data["crawl_status"] = "idle"
        site_updated = await repos.sites.update(site_id, update_data)

        return {
            "message": f"Crawl đã TẮT cho {site['name']}. Dữ liệu đã học được giữ nguyên ({site.get('knowledge_count', 0)} chunks).",
            "crawl_enabled": False,
            "crawl_status": "idle",
            "knowledge_count": site.get("knowledge_count", 0),
        }


# ============================================================
# 2. START CRAWL — Chạy thủ công (không cần bật toggle)
# ============================================================

@router.post("/start")
async def start_crawl(
    data: CrawlStartRequest,
    background_tasks: BackgroundTasks,
    repos: Repositories = Depends(get_repos),
):
    """Trigger crawl thủ công, bất kể crawl_enabled."""
    site = await repos.sites.get_by_id(data.site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    if site.get("crawl_status") == "running":
        raise HTTPException(status_code=409, detail="Crawl đang chạy. Hãy dừng trước khi bắt đầu lại.")

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
        "message": f"Đang crawl {crawl_url}",
    }


# ============================================================
# 3. STOP CRAWL — Dừng crawl đang chạy
# ============================================================

@router.post("/stop/{site_id}")
async def stop_crawl(
    site_id: str,
    repos: Repositories = Depends(get_repos),
):
    """Dừng crawl đang chạy. Dữ liệu đã crawl được giữ lại trong DB."""
    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    if site_id in _active_crawlers:
        _active_crawlers[site_id].stop()
        del _active_crawlers[site_id]

    await repos.sites.update(site_id, {"crawl_status": "idle"})

    return {
        "message": f"Đã dừng crawl. Giữ lại {site.get('knowledge_count', 0)} chunks đã học.",
        "crawl_status": "idle",
        "knowledge_count": site.get("knowledge_count", 0),
    }


# ============================================================
# 4. STATUS — Xem trạng thái crawl
# ============================================================

@router.get("/status/{site_id}")
async def get_crawl_status(
    site_id: str,
    repos: Repositories = Depends(get_repos),
):
    """Xem trạng thái crawl hiện tại của site."""
    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    return {
        "site_id": site_id,
        "crawl_enabled": site.get("crawl_enabled", False),
        "crawl_status": site.get("crawl_status", "idle"),
        "crawl_auto_interval": site.get("crawl_auto_interval", 0),
        "crawl_max_pages": site.get("crawl_max_pages", 50),
        "knowledge_count": site.get("knowledge_count", 0),
        "last_crawled_at": site.get("last_crawled_at"),
        "is_running": site_id in _active_crawlers,
    }


# ============================================================
# 5. JOBS — Lịch sử crawl
# ============================================================

@router.get("/jobs/{site_id}")
async def get_crawl_jobs(
    site_id: str,
    repos: Repositories = Depends(get_repos),
):
    return await repos.crawl_jobs.list_by_site(site_id)


@router.get("/job/{job_id}")
async def get_crawl_job(
    job_id: str,
    repos: Repositories = Depends(get_repos),
):
    job = await repos.crawl_jobs.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")
    return job


# ============================================================
# 6. CLEAR KNOWLEDGE — Xóa toàn bộ data đã học
# ============================================================

@router.delete("/knowledge/{site_id}")
async def clear_knowledge(
    site_id: str,
    repos: Repositories = Depends(get_repos),
):
    """Xóa toàn bộ knowledge đã crawl của site."""
    from agent.rag import rag_engine

    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Xóa từ vector store
    await rag_engine.delete_site(site_id)

    # Xóa từ DB — lấy tất cả chunks rồi xóa
    data = await repos.knowledge.list_by_site(site_id, page=1, per_page=10000)
    for chunk in data.get("chunks", []):
        await repos.knowledge.delete(chunk["id"])

    await repos.sites.update(site_id, {"knowledge_count": 0})

    return {
        "message": f"Đã xóa toàn bộ knowledge của {site['name']}.",
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
    """Background task: crawl + update site status when done."""
    repos = await get_repos()

    crawler = WebCrawler(max_pages=max_pages)
    _active_crawlers[site_id] = crawler

    try:
        await crawler.crawl_site(site_id, url, job_id, repos)

        # Update site stats
        knowledge_data = await repos.knowledge.list_by_site(site_id, page=1, per_page=1)
        total_chunks = knowledge_data.get("total", 0)

        await repos.sites.update(site_id, {
            "crawl_status": "idle",
            "last_crawled_at": datetime.utcnow().isoformat(),
            "knowledge_count": total_chunks,
        })
    except Exception as e:
        await repos.sites.update(site_id, {"crawl_status": "idle"})
        await repos.crawl_jobs.update(job_id, {
            "status": "failed",
            "error_log": str(e),
        })
    finally:
        _active_crawlers.pop(site_id, None)
