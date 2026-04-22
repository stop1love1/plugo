"""Memory management router — view, edit, delete visitor memories."""


from auth import TokenData, get_current_user
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from repositories import Repositories, get_repos

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryUpdate(BaseModel):
    value: str | None = None
    category: str | None = None
    confidence: str | None = None


@router.get("/visitors")
async def list_visitors_with_memories(
    site_id: str = Query(...),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """List unique visitors that have memories for a site."""
    # Get all memories for this site in a single query, then group by visitor_id
    all_memories = await repos.visitor_memories.list_by_site(site_id)

    visitor_map: dict[str, dict] = {}
    for mem in all_memories:
        vid = mem.get("visitor_id")
        if not vid:
            continue
        if vid not in visitor_map:
            visitor_map[vid] = {
                "visitor_id": vid,
                "memory_count": 0,
                "last_updated": mem.get("updated_at"),
            }
        entry = visitor_map[vid]
        entry["memory_count"] += 1
        lu = mem.get("updated_at")
        if lu and (not entry.get("last_updated") or lu > entry["last_updated"]):
            entry["last_updated"] = lu

    return list(visitor_map.values())


@router.get("/visitor/{visitor_id}")
async def get_visitor_memories(
    visitor_id: str,
    site_id: str = Query(...),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Get all memories for a specific visitor."""
    return await repos.visitor_memories.list_by_visitor(visitor_id, site_id)


@router.put("/{memory_id}")
async def update_memory(
    memory_id: str,
    data: MemoryUpdate,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Update a specific memory entry."""
    existing = await repos.visitor_memories.get_by_id(memory_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Memory not found")

    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        return existing

    # Use upsert with existing keys
    return await repos.visitor_memories.upsert(
        visitor_id=existing["visitor_id"],
        site_id=existing["site_id"],
        key=existing["key"],
        data=update_data,
    )


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Delete a specific memory entry."""
    deleted = await repos.visitor_memories.delete(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": True}


@router.delete("/visitor/{visitor_id}")
async def delete_visitor_memories(
    visitor_id: str,
    site_id: str = Query(...),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Delete all memories for a visitor (GDPR compliance)."""
    count = await repos.visitor_memories.delete_by_visitor(visitor_id, site_id)
    return {"deleted_count": count}


@router.get("/summaries")
async def get_session_summary(
    session_id: str = Query(...),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Get the conversation summary for a session."""
    summary = await repos.conversation_summaries.get_by_session(session_id)
    if not summary:
        return {"summary": None}
    return summary
