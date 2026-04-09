import json
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from agent.rag import rag_engine
from auth import TokenData, get_current_user
from config import settings
from logging_config import logger
from providers.factory import get_llm_provider
from repositories import Repositories, get_repos

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5MB
MAX_PER_PAGE = 100


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


@router.post("/url/recrawl")
async def recrawl_url(
    data: RecrawlUrlRequest,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Delete existing chunks for a URL, then re-crawl that single page."""
    from knowledge.crawler import WebCrawler

    # Delete old chunks for this URL first
    old_chunks = await repos.knowledge.list_by_url(data.site_id, data.source_url)
    if old_chunks:
        embedding_ids = [c.get("embedding_id") or c["id"] for c in old_chunks]
        await rag_engine.delete_chunks(data.site_id, embedding_ids)
        await repos.knowledge.delete_by_url(data.site_id, data.source_url)

    # Crawl single page
    crawler = WebCrawler(max_pages=1, delay=0)
    job = await repos.crawl_jobs.create({
        "site_id": data.site_id,
        "start_url": data.source_url,
    })

    try:
        await crawler.crawl_site(data.site_id, data.source_url, job["id"], repos)

        # Update site knowledge count
        knowledge_data = await repos.knowledge.list_by_site(data.site_id, page=1, per_page=1)
        await repos.sites.update(data.site_id, {"knowledge_count": knowledge_data.get("total", 0)})

        new_chunks = await repos.knowledge.list_by_url(data.site_id, data.source_url)
        return {
            "message": f"Re-crawled {data.source_url}",
            "old_chunks": len(old_chunks),
            "new_chunks": len(new_chunks),
            "job_id": job["id"],
        }
    except Exception as e:
        logger.error("Recrawl failed", url=data.source_url, error=str(e))
        raise HTTPException(status_code=500, detail=f"Recrawl failed: {e!s}") from e


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
        raise HTTPException(status_code=400, detail=str(e))

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
