import json
import time
import uuid

from auth import TokenData, get_current_user
from config import settings
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from logging_config import logger
from pydantic import BaseModel, Field

from agent.rag import rag_engine
from providers.factory import get_llm_provider
from repositories import Repositories, create_repos, get_repos

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5MB
MAX_PER_PAGE = 100
# Synchronous reindex is bounded by the HTTP request timeout. Above this
# chunk count, the CLI (`backend/manage.py reindex <site_id>`) is the supported
# path — it doesn't race the request/response deadline and prints progress.
REINDEX_SYNC_MAX = 1000
REINDEX_BATCH_SIZE = 100
# Page size used when the reindex helper pulls every chunk for a site. Kept
# well below `REINDEX_SYNC_MAX` so the CLI path (which has no upper bound)
# can stream through arbitrarily large sites without huge single queries.
REINDEX_FETCH_PAGE_SIZE = 200


@router.get("")
async def list_knowledge(
    site_id: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=MAX_PER_PAGE),
    search: str | None = None,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    data = await repos.knowledge.list_by_site(site_id, page, per_page, search=search)
    chunks = data.get("chunks", [])

    # Truncate content for list view
    for chunk in chunks:
        if len(chunk.get("content", "")) > 200:
            chunk["content"] = chunk["content"][:200] + "..."
    return data


# NOTE: Static path routes (/urls, /url/*, /bulk-delete) MUST be defined
# BEFORE dynamic path routes (/{chunk_id}) to avoid FastAPI route conflicts.

@router.get("/urls")
async def list_crawled_urls(
    site_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """List all unique crawled URLs for a site with chunk counts."""
    return await repos.knowledge.list_crawled_urls(site_id)


@router.get("/url/chunks")
async def get_chunks_by_url(
    site_id: str,
    source_url: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Get all chunks from a specific crawled URL."""
    chunks = await repos.knowledge.list_by_url(site_id, source_url)
    return {"chunks": chunks, "total": len(chunks), "source_url": source_url}


@router.get("/{chunk_id}")
async def get_chunk(
    chunk_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    chunk = await repos.knowledge.get_by_id(chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    return chunk


@router.delete("/{chunk_id}")
async def delete_chunk(
    chunk_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    chunk = await repos.knowledge.get_by_id(chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    await rag_engine.delete_chunks(chunk["site_id"], [chunk.get("embedding_id") or chunk["id"]])
    await repos.knowledge.delete(chunk_id)
    return {"message": "Chunk deleted"}


class ChunkUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    content: str | None = Field(None, min_length=1, max_length=50000)


@router.put("/{chunk_id}")
async def update_chunk(
    chunk_id: str,
    data: ChunkUpdate,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    chunk = await repos.knowledge.get_by_id(chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = await repos.knowledge.update(chunk_id, update_data)

    # Re-embed if content changed
    if "content" in update_data:
        try:
            embed_provider = get_llm_provider(settings.embedding_provider, settings.embedding_model)
            embeddings = await embed_provider.embed([updated["content"]])
            await rag_engine.delete_chunks(chunk["site_id"], [chunk.get("embedding_id") or chunk["id"]])
            await rag_engine.add_chunks(
                chunk["site_id"],
                [{"id": chunk_id, "content": updated["content"], "source_url": chunk.get("source_url", ""), "title": updated.get("title", chunk.get("title", "")), "chunk_index": 0}],
                embeddings,
            )
        except Exception as e:
            logger.warning("Failed to re-embed updated chunk", error=str(e), chunk_id=chunk_id)

    return {"message": "Chunk updated", "chunk": updated}


class BulkDeleteRequest(BaseModel):
    chunk_ids: list[str] = Field(min_length=1, max_length=100)


@router.post("/bulk-delete")
async def bulk_delete_chunks(
    data: BulkDeleteRequest,
    repos: Repositories = Depends(get_repos),
    user: TokenData = Depends(get_current_user),
):
    """Delete multiple chunks at once."""
    # Batch fetch all chunks in a single query
    chunks = await repos.knowledge.get_many(data.chunk_ids)

    # Batch delete from vector store grouped by site_id
    site_embedding_ids: dict[str, list[str]] = {}
    for chunk in chunks:
        sid = chunk["site_id"]
        eid = chunk.get("embedding_id") or chunk["id"]
        site_embedding_ids.setdefault(sid, []).append(eid)
    for sid, eids in site_embedding_ids.items():
        await rag_engine.delete_chunks(sid, eids)

    # Batch delete from database
    chunk_ids_to_delete = [c["id"] for c in chunks]
    if chunk_ids_to_delete:
        await repos.knowledge.delete_many(chunk_ids_to_delete)
    deleted = len(chunks)
    try:
        await repos.audit_logs.create({
            "user_id": user.sub,
            "username": user.sub,
            "action": "delete",
            "resource_type": "knowledge",
            "resource_id": None,
            "details": json.dumps({"deleted_count": deleted, "chunk_ids": data.chunk_ids[:10]}),
        })
    except Exception as e:
        logger.warning("Failed to create audit log", error=str(e))
    return {"deleted": deleted}


class DeleteByUrlRequest(BaseModel):
    site_id: str
    source_url: str


@router.post("/url/delete")
async def delete_by_url(
    data: DeleteByUrlRequest,
    repos: Repositories = Depends(get_repos),
    user: TokenData = Depends(get_current_user),
):
    """Delete all chunks from a specific URL (and from vector store)."""
    chunks = await repos.knowledge.list_by_url(data.site_id, data.source_url)
    if not chunks:
        raise HTTPException(status_code=404, detail="No chunks found for this URL")

    # Delete from vector store
    embedding_ids = [c.get("embedding_id") or c["id"] for c in chunks]
    await rag_engine.delete_chunks(data.site_id, embedding_ids)

    # Delete from database
    deleted = await repos.knowledge.delete_by_url(data.site_id, data.source_url)

    # Update site knowledge count
    knowledge_data = await repos.knowledge.list_by_site(data.site_id, page=1, per_page=1)
    await repos.sites.update(data.site_id, {"knowledge_count": knowledge_data.get("total", 0)})

    try:
        await repos.audit_logs.create({
            "user_id": user.sub, "username": user.sub,
            "action": "delete", "resource_type": "knowledge",
            "resource_id": None,
            "details": json.dumps({"source_url": data.source_url, "deleted_count": deleted}),
        })
    except Exception as e:
        logger.warning("Failed to create audit log", error=str(e))

    return {"deleted": deleted, "source_url": data.source_url}


class RecrawlUrlRequest(BaseModel):
    site_id: str
    source_url: str


async def _run_recrawl(site_id: str, source_url: str, job_id: str):
    """Background task: re-crawl a single URL and update knowledge count."""
    from knowledge.crawler import WebCrawler

    repos = await create_repos()
    try:
        crawler = WebCrawler(max_pages=1, delay=0)
        await crawler.crawl_site(site_id, source_url, job_id, repos)

        # Update site knowledge count
        knowledge_data = await repos.knowledge.list_by_site(site_id, page=1, per_page=1)
        await repos.sites.update(site_id, {"knowledge_count": knowledge_data.get("total", 0)})
    except Exception as e:
        logger.error("Recrawl failed", url=source_url, error=str(e))
    finally:
        await repos.close()


@router.post("/url/recrawl", status_code=202)
async def recrawl_url(
    data: RecrawlUrlRequest,
    background_tasks: BackgroundTasks,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Delete existing chunks for a URL, then re-crawl that single page in the background."""
    # Delete old chunks for this URL first
    old_chunks = await repos.knowledge.list_by_url(data.site_id, data.source_url)
    if old_chunks:
        embedding_ids = [c.get("embedding_id") or c["id"] for c in old_chunks]
        await rag_engine.delete_chunks(data.site_id, embedding_ids)
        await repos.knowledge.delete_by_url(data.site_id, data.source_url)

    job = await repos.crawl_jobs.create({
        "site_id": data.site_id,
        "start_url": data.source_url,
    })

    background_tasks.add_task(_run_recrawl, data.site_id, data.source_url, job["id"])

    return JSONResponse(
        status_code=202,
        content={
            "message": f"Re-crawl started for {data.source_url}",
            "old_chunks": len(old_chunks),
            "job_id": job["id"],
        },
    )


async def _reindex_site(
    site_id: str,
    repos: Repositories,
    progress_cb=None,
) -> dict:
    """Rebuild ChromaDB embeddings for every chunk on `site_id`.

    Shared by the HTTP endpoint and the `manage.py reindex` CLI. Deletes
    the site's existing Chroma collection, then re-embeds each chunk in
    batches using the CURRENT `settings.embedding_provider` — so this is
    the correct recovery path after swapping embedding models.

    `progress_cb(done, total)` lets the CLI print a progress bar; the HTTP
    path passes None and just gets the summary dict back.

    This helper itself has NO upper bound on chunk count — the HTTP caller
    enforces `REINDEX_SYNC_MAX`, while the CLI relies on this pagination loop
    to handle arbitrarily large sites.
    """
    start = time.monotonic()
    # Paginate through every chunk — do NOT cap at REINDEX_SYNC_MAX here,
    # or the CLI path will silently truncate large sites and wipe Chroma
    # without restoring the missing chunks.
    chunks: list[dict] = []
    page_num = 1
    while True:
        page = await repos.knowledge.list_by_site(
            site_id, page=page_num, per_page=REINDEX_FETCH_PAGE_SIZE
        )
        page_chunks = page.get("chunks", []) or []
        if not page_chunks:
            break
        chunks.extend(page_chunks)
        reported_total = int(page.get("total") or 0)
        # Stop when we've pulled everything reported, or when the last page
        # came back short (fallback if `total` is missing/unreliable).
        if reported_total and len(chunks) >= reported_total:
            break
        if len(page_chunks) < REINDEX_FETCH_PAGE_SIZE:
            break
        page_num += 1
    total = len(chunks)

    # Wipe the whole collection rather than deleting ids one by one — matches
    # what the admin intent is: "start fresh with the new embedding model".
    await rag_engine.delete_site(site_id)

    if total == 0:
        return {"chunks_reindexed": 0, "elapsed_seconds": round(time.monotonic() - start, 3)}

    embed_provider = get_llm_provider(settings.embedding_provider, settings.embedding_model)
    done = 0
    for i in range(0, total, REINDEX_BATCH_SIZE):
        batch = chunks[i : i + REINDEX_BATCH_SIZE]
        contents = [c["content"] for c in batch]
        embeddings = await embed_provider.embed(contents)
        vector_chunks = [
            {
                "id": c.get("embedding_id") or c["id"],
                "content": c["content"],
                "source_url": c.get("source_url") or "",
                "title": c.get("title") or "",
                "chunk_index": c.get("chunk_index", 0),
            }
            for c in batch
        ]
        await rag_engine.add_chunks(site_id, vector_chunks, embeddings)
        done += len(batch)
        if progress_cb:
            progress_cb(done, total)

    return {"chunks_reindexed": done, "elapsed_seconds": round(time.monotonic() - start, 3)}


@router.post("/reindex")
async def reindex_site(
    site_id: str,
    repos: Repositories = Depends(get_repos),
    user: TokenData = Depends(get_current_user),
):
    """Rebuild ChromaDB embeddings for every chunk on a site.

    Required after swapping `settings.embedding_provider`/model. Synchronous
    for sites with ≤ REINDEX_SYNC_MAX chunks; larger sites must use the
    `manage.py reindex <site_id>` CLI to avoid blocking the request.
    """
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    site = await repos.sites.get_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Cheap count — avoid loading every chunk twice.
    count_page = await repos.knowledge.list_by_site(site_id, page=1, per_page=1)
    total = int(count_page.get("total") or 0)
    if total > REINDEX_SYNC_MAX:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Site has {total} chunks (> {REINDEX_SYNC_MAX}). "
                f"Use `python backend/manage.py reindex {site_id}` from the CLI."
            ),
        )

    result = await _reindex_site(site_id, repos)

    try:
        await repos.audit_logs.create({
            "user_id": user.sub,
            "username": user.sub,
            "action": "reindex",
            "resource_type": "knowledge",
            "resource_id": site_id,
            "details": json.dumps({
                "site_id": site_id,
                "chunks_reindexed": result["chunks_reindexed"],
                "embedding_provider": settings.embedding_provider,
                "embedding_model": settings.embedding_model,
            }),
        })
    except Exception as e:
        logger.warning("Failed to create reindex audit log", error=str(e))

    return {"status": "ok", **result}


class ManualChunkCreate(BaseModel):
    site_id: str
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=50000)
    source_url: str | None = None


@router.post("/manual")
async def add_manual_chunk(
    data: ManualChunkCreate,
    repos: Repositories = Depends(get_repos),
    user: TokenData = Depends(get_current_user),
):
    chunk_id = str(uuid.uuid4())
    embedding_ok = False

    try:
        embed_provider = get_llm_provider(settings.embedding_provider, settings.embedding_model)
        embeddings = await embed_provider.embed([data.content])
        await rag_engine.add_chunks(
            data.site_id,
            [{"id": chunk_id, "content": data.content, "source_url": data.source_url or "", "title": data.title, "chunk_index": 0}],
            embeddings,
        )
        embedding_ok = True
    except Exception as e:
        logger.warning("Failed to generate embeddings for manual chunk", error=str(e), chunk_id=chunk_id)

    await repos.knowledge.create({
        "id": chunk_id,
        "site_id": data.site_id,
        "source_url": data.source_url,
        "source_type": "manual",
        "title": data.title,
        "content": data.content,
        "embedding_id": chunk_id,
    })
    try:
        await repos.audit_logs.create({
            "user_id": user.sub,
            "username": user.sub,
            "action": "create",
            "resource_type": "knowledge",
            "resource_id": chunk_id,
            "details": json.dumps({"title": data.title, "site_id": data.site_id}),
        })
    except Exception as e:
        logger.warning("Failed to create audit log", error=str(e))
    return {
        "id": chunk_id,
        "message": "Chunk added",
        "embedding": "ok" if embedding_ok else "failed — chunk saved but may not appear in search",
    }


SUPPORTED_UPLOAD_EXTENSIONS = (".txt", ".md", ".pdf", ".docx", ".csv")


@router.post("/upload")
async def upload_file(
    site_id: str,
    file: UploadFile = File(...),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    from knowledge.chunker import SemanticChunker
    from knowledge.file_processor import extract_text

    # Validate extension
    filename = file.filename or "unknown.txt"
    if not any(filename.lower().endswith(ext) for ext in SUPPORTED_UPLOAD_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"Supported formats: {', '.join(SUPPORTED_UPLOAD_EXTENSIONS)}",
        )

    # Validate file size
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Maximum size: {MAX_UPLOAD_SIZE // (1024*1024)}MB")

    # Extract text
    try:
        text = extract_text(content, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not text.strip():
        raise HTTPException(status_code=400, detail="File is empty or no text could be extracted")

    # Chunk the text properly
    chunker = SemanticChunker()
    source_url = f"upload://{filename}"
    chunks = chunker.chunk_plain_text(text, filename, source_url, site_id)

    if not chunks:
        raise HTTPException(status_code=400, detail="No content could be extracted from file")

    # Embed and store all chunks
    embedding_ok = False
    try:
        embed_provider = get_llm_provider(settings.embedding_provider, settings.embedding_model)
        contents = [c["content"] for c in chunks]
        embeddings = await embed_provider.embed(contents)
        await rag_engine.add_chunks(site_id, chunks, embeddings)
        embedding_ok = True
    except Exception as e:
        logger.warning("Failed to generate embeddings for uploaded file", error=str(e), filename=filename)

    # Store in database (bulk)
    db_chunks = []
    for chunk in chunks:
        db_chunks.append({
            "id": chunk["id"],
            "site_id": site_id,
            "source_url": source_url,
            "source_type": "upload",
            "title": filename,
            "content": chunk["content"],
            "chunk_index": chunk.get("chunk_index", 0),
            "content_hash": chunk.get("content_hash", ""),
            "embedding_id": chunk["id"],
        })
    await repos.knowledge.create_many(db_chunks)

    return {
        "filename": filename,
        "message": f"File uploaded — {len(chunks)} chunks created",
        "chunks_created": len(chunks),
        "embedding": "ok" if embedding_ok else "failed — file saved but may not appear in search",
    }
