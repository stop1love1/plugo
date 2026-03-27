import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional
from repositories import get_repos, Repositories
from agent.rag import rag_engine
from providers.factory import get_llm_provider
from config import settings

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("")
async def list_knowledge(
    site_id: str,
    page: int = 1,
    per_page: int = 20,
    repos: Repositories = Depends(get_repos),
):
    data = await repos.knowledge.list_by_site(site_id, page, per_page)
    # Truncate content for list view
    for chunk in data.get("chunks", []):
        if len(chunk.get("content", "")) > 200:
            chunk["content"] = chunk["content"][:200] + "..."
    return data


@router.get("/{chunk_id}")
async def get_chunk(chunk_id: str, repos: Repositories = Depends(get_repos)):
    chunk = await repos.knowledge.get_by_id(chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    return chunk


@router.delete("/{chunk_id}")
async def delete_chunk(chunk_id: str, repos: Repositories = Depends(get_repos)):
    chunk = await repos.knowledge.get_by_id(chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    await rag_engine.delete_chunks(chunk["site_id"], [chunk.get("embedding_id") or chunk["id"]])
    await repos.knowledge.delete(chunk_id)
    return {"message": "Chunk deleted"}


class ManualChunkCreate(BaseModel):
    site_id: str
    title: str
    content: str
    source_url: Optional[str] = None


@router.post("/manual")
async def add_manual_chunk(data: ManualChunkCreate, repos: Repositories = Depends(get_repos)):
    chunk_id = str(uuid.uuid4())

    try:
        embed_provider = get_llm_provider(settings.embedding_provider, settings.embedding_model)
        embeddings = await embed_provider.embed([data.content])
        await rag_engine.add_chunks(
            data.site_id,
            [{"id": chunk_id, "content": data.content, "source_url": data.source_url or "", "title": data.title, "chunk_index": 0}],
            embeddings,
        )
    except Exception:
        pass

    await repos.knowledge.create({
        "id": chunk_id,
        "site_id": data.site_id,
        "source_url": data.source_url,
        "source_type": "manual",
        "title": data.title,
        "content": data.content,
        "embedding_id": chunk_id,
    })
    return {"id": chunk_id, "message": "Chunk added"}


@router.post("/upload")
async def upload_file(
    site_id: str,
    file: UploadFile = File(...),
    repos: Repositories = Depends(get_repos),
):
    content = await file.read()
    text = ""

    if file.filename.endswith(".txt") or file.filename.endswith(".md"):
        text = content.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(status_code=400, detail="Supported formats: .txt, .md")

    if not text.strip():
        raise HTTPException(status_code=400, detail="File is empty")

    chunk_id = str(uuid.uuid4())
    await repos.knowledge.create({
        "id": chunk_id,
        "site_id": site_id,
        "source_type": "upload",
        "title": file.filename,
        "content": text[:10000],
        "embedding_id": chunk_id,
    })

    try:
        embed_provider = get_llm_provider(settings.embedding_provider, settings.embedding_model)
        embeddings = await embed_provider.embed([text[:10000]])
        await rag_engine.add_chunks(
            site_id,
            [{"id": chunk_id, "content": text[:10000], "source_url": "", "title": file.filename, "chunk_index": 0}],
            embeddings,
        )
    except Exception:
        pass

    return {"id": chunk_id, "filename": file.filename, "message": "File uploaded"}
