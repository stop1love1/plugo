"""Flow guides — CRUD + RAG sync for step-by-step website flow guides."""

import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from agent.rag import rag_engine
from auth import TokenData, get_current_user
from config import settings
from logging_config import logger
from providers.factory import get_llm_provider
from repositories import Repositories, get_repos

router = APIRouter(prefix="/api/flows", tags=["flows"])

SCREENSHOT_DIR = "data/screenshots"


# ============================================================
# Request models
# ============================================================

class FlowCreate(BaseModel):
    site_id: str
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    requires_login: bool = False


class FlowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    requires_login: bool | None = None
    is_enabled: bool | None = None


class FlowStepCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    url: str | None = None


class FlowStepUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    url: str | None = None
    screenshot_url: str | None = None


class ReorderStepsRequest(BaseModel):
    step_ids: list[str]


# ============================================================
# Flow CRUD
# ============================================================

@router.get("")
async def list_flows(
    site_id: str = Query(...),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    flows = await repos.flows.list_by_site(site_id)
    # Attach step count to each flow
    for flow in flows:
        steps = await repos.flow_steps.list_by_flow(flow["id"])
        flow["step_count"] = len(steps)
    return flows


@router.post("")
async def create_flow(
    data: FlowCreate,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    flow = await repos.flows.create(data.model_dump())
    return {"id": flow["id"], "message": "Flow created"}


@router.get("/{flow_id}")
async def get_flow(
    flow_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    flow = await repos.flows.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    flow["steps"] = await repos.flow_steps.list_by_flow(flow_id)
    return flow


@router.put("/{flow_id}")
async def update_flow(
    flow_id: str,
    data: FlowUpdate,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    flow = await repos.flows.update(flow_id, update_data)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    # Auto-sync to RAG when flow metadata changes
    steps = await repos.flow_steps.list_by_flow(flow_id)
    if steps:
        await _sync_flow_to_rag(flow, steps, repos)

    return {"message": "Flow updated"}


@router.delete("/{flow_id}")
async def delete_flow(
    flow_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    flow = await repos.flows.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    # Delete from RAG
    source_url = f"flow://{flow_id}"
    old_chunks = await repos.knowledge.list_by_url(flow["site_id"], source_url)
    if old_chunks:
        embedding_ids = [c.get("embedding_id") or c["id"] for c in old_chunks]
        await rag_engine.delete_chunks(flow["site_id"], embedding_ids)
        await repos.knowledge.delete_by_url(flow["site_id"], source_url)

    await repos.flows.delete(flow_id)
    return {"message": "Flow deleted"}


# ============================================================
# Flow Steps CRUD
# ============================================================

@router.post("/{flow_id}/steps")
async def add_step(
    flow_id: str,
    data: FlowStepCreate,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    flow = await repos.flows.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    # Auto-assign step_order as next in sequence
    existing_steps = await repos.flow_steps.list_by_flow(flow_id)
    next_order = len(existing_steps) + 1

    step_data = data.model_dump()
    step_data["flow_id"] = flow_id
    step_data["step_order"] = next_order
    step = await repos.flow_steps.create(step_data)

    # Auto-sync to RAG
    all_steps = await repos.flow_steps.list_by_flow(flow_id)
    await _sync_flow_to_rag(flow, all_steps, repos)

    return {"id": step["id"], "message": "Step added", "step_order": next_order}


@router.put("/steps/{step_id}")
async def update_step(
    step_id: str,
    data: FlowStepUpdate,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    step = await repos.flow_steps.update(step_id, update_data)
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    # Auto-sync to RAG
    flow = await repos.flows.get_by_id(step["flow_id"])
    if flow:
        all_steps = await repos.flow_steps.list_by_flow(step["flow_id"])
        await _sync_flow_to_rag(flow, all_steps, repos)

    return {"message": "Step updated"}


@router.delete("/steps/{step_id}")
async def delete_step(
    step_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    step = await repos.flow_steps.get_by_id(step_id)
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    flow_id = step["flow_id"]
    await repos.flow_steps.delete(step_id)

    # Re-order remaining steps
    remaining = await repos.flow_steps.list_by_flow(flow_id)
    if remaining:
        step_ids = [s["id"] for s in remaining]
        await repos.flow_steps.reorder(flow_id, step_ids)

    # Auto-sync to RAG
    flow = await repos.flows.get_by_id(flow_id)
    if flow:
        updated_steps = await repos.flow_steps.list_by_flow(flow_id)
        if updated_steps:
            await _sync_flow_to_rag(flow, updated_steps, repos)
        else:
            # No steps left — remove from RAG
            source_url = f"flow://{flow_id}"
            old_chunks = await repos.knowledge.list_by_url(flow["site_id"], source_url)
            if old_chunks:
                embedding_ids = [c.get("embedding_id") or c["id"] for c in old_chunks]
                await rag_engine.delete_chunks(flow["site_id"], embedding_ids)
                await repos.knowledge.delete_by_url(flow["site_id"], source_url)

    return {"message": "Step deleted"}


@router.post("/{flow_id}/reorder")
async def reorder_steps(
    flow_id: str,
    data: ReorderStepsRequest,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    flow = await repos.flows.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    await repos.flow_steps.reorder(flow_id, data.step_ids)

    # Auto-sync to RAG
    steps = await repos.flow_steps.list_by_flow(flow_id)
    if steps:
        await _sync_flow_to_rag(flow, steps, repos)

    return {"message": "Steps reordered"}


# ============================================================
# Screenshot upload
# ============================================================

@router.post("/steps/{step_id}/screenshot")
async def upload_screenshot(
    step_id: str,
    file: UploadFile = File(...),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    step = await repos.flow_steps.get_by_id(step_id)
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Screenshot too large (max 5MB)")

    # Save to data/screenshots/{flow_id}/
    flow_dir = os.path.join(SCREENSHOT_DIR, step["flow_id"])
    os.makedirs(flow_dir, exist_ok=True)

    ext = os.path.splitext(file.filename or "image.png")[1] or ".png"
    filename = f"{step_id}{ext}"
    filepath = os.path.join(flow_dir, filename)

    with open(filepath, "wb") as f:
        f.write(content)

    screenshot_url = f"/api/flows/screenshots/{step['flow_id']}/{filename}"
    await repos.flow_steps.update(step_id, {"screenshot_url": screenshot_url})

    return {"message": "Screenshot uploaded", "screenshot_url": screenshot_url}


@router.get("/screenshots/{flow_id}/{filename}")
async def serve_screenshot(flow_id: str, filename: str):
    """Serve uploaded screenshot files."""
    from fastapi.responses import FileResponse
    # Sanitize inputs to prevent path traversal
    safe_flow_id = os.path.basename(flow_id)
    safe_filename = os.path.basename(filename)
    if not safe_flow_id or not safe_filename or ".." in flow_id or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid path")
    filepath = os.path.join(SCREENSHOT_DIR, safe_flow_id, safe_filename)
    # Verify resolved path is within SCREENSHOT_DIR
    if not os.path.abspath(filepath).startswith(os.path.abspath(SCREENSHOT_DIR)):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(filepath)


# ============================================================
# Sync to RAG
# ============================================================

@router.post("/{flow_id}/sync")
async def sync_flow(
    flow_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    flow = await repos.flows.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    steps = await repos.flow_steps.list_by_flow(flow_id)
    if not steps:
        raise HTTPException(status_code=400, detail="Flow has no steps")

    await _sync_flow_to_rag(flow, steps, repos)
    return {"message": "Flow synced to knowledge base"}


# ============================================================
# Internal helpers
# ============================================================

async def _sync_flow_to_rag(flow: dict, steps: list[dict], repos: Repositories):
    """Convert a flow into a structured text chunk and embed it into RAG."""
    site_id = flow["site_id"]
    source_url = f"flow://{flow['id']}"

    # Build structured text
    lines = [f"FLOW GUIDE: {flow['name']}"]
    if flow.get("description"):
        lines.append(f"Description: {flow['description']}")
    if flow.get("requires_login"):
        lines.append("Requires login: Yes — user must be logged in to follow these steps.")
    lines.append("")

    for step in sorted(steps, key=lambda s: s["step_order"]):
        lines.append(f"Step {step['step_order']}: {step['title']}")
        if step.get("description"):
            lines.append(step["description"])
        if step.get("url"):
            lines.append(f"URL: {step['url']}")
        lines.append("")

    content = "\n".join(lines).strip()

    # Delete old flow chunk if exists
    old_chunks = await repos.knowledge.list_by_url(site_id, source_url)
    if old_chunks:
        embedding_ids = [c.get("embedding_id") or c["id"] for c in old_chunks]
        await rag_engine.delete_chunks(site_id, embedding_ids)
        await repos.knowledge.delete_by_url(site_id, source_url)

    # Create new chunk — only save to DB if embedding succeeds
    chunk_id = str(uuid.uuid4())
    try:
        embed_provider = get_llm_provider(settings.embedding_provider, settings.embedding_model)
        embeddings = await embed_provider.embed([content])
        await rag_engine.add_chunks(site_id, [{
            "id": chunk_id,
            "content": content,
            "source_url": source_url,
            "title": f"Flow: {flow['name']}",
            "chunk_index": 0,
        }], embeddings)

        await repos.knowledge.create({
            "id": chunk_id,
            "site_id": site_id,
            "source_url": source_url,
            "source_type": "flow",
            "title": f"Flow: {flow['name']}",
            "content": content,
            "embedding_id": chunk_id,
        })
    except Exception as e:
        logger.warning("Failed to embed flow", flow_id=flow["id"], error=str(e))
