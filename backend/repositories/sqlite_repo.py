"""SQLite implementation using SQLAlchemy async."""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.base import (
    BaseSiteRepo, BaseKnowledgeRepo, BaseToolRepo,
    BaseChatSessionRepo, BaseCrawlJobRepo,
)
from models.site import Site
from models.knowledge import KnowledgeChunk
from models.tool import Tool
from models.chat import ChatSession
from models.crawl import CrawlJob


def _site_to_dict(s: Site) -> dict:
    return {
        "id": s.id, "name": s.name, "url": s.url, "token": s.token,
        "llm_provider": s.llm_provider, "llm_model": s.llm_model,
        "primary_color": s.primary_color, "greeting": s.greeting,
        "position": s.position, "allowed_domains": s.allowed_domains or "",
        # Crawl management
        "crawl_enabled": s.crawl_enabled,
        "crawl_auto_interval": s.crawl_auto_interval,
        "crawl_max_pages": s.crawl_max_pages,
        "crawl_status": s.crawl_status,
        "last_crawled_at": s.last_crawled_at.isoformat() if s.last_crawled_at else None,
        "knowledge_count": s.knowledge_count,
        # Timestamps
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _chunk_to_dict(c: KnowledgeChunk) -> dict:
    return {
        "id": c.id, "site_id": c.site_id, "source_url": c.source_url,
        "source_type": c.source_type, "title": c.title, "content": c.content,
        "chunk_index": c.chunk_index, "embedding_id": c.embedding_id,
        "crawled_at": c.crawled_at.isoformat() if c.crawled_at else None,
    }


def _tool_to_dict(t: Tool) -> dict:
    return {
        "id": t.id, "site_id": t.site_id, "name": t.name,
        "description": t.description, "method": t.method, "url": t.url,
        "params_schema": t.params_schema, "headers": t.headers,
        "auth_type": t.auth_type, "auth_value": t.auth_value,
        "enabled": t.enabled,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _session_to_dict(s: ChatSession) -> dict:
    return {
        "id": s.id, "site_id": s.site_id, "visitor_id": s.visitor_id,
        "page_url": s.page_url, "messages": s.messages or [],
        "message_count": len(s.messages) if s.messages else 0,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
    }


def _job_to_dict(j: CrawlJob) -> dict:
    return {
        "id": j.id, "site_id": j.site_id, "status": j.status,
        "start_url": j.start_url, "pages_found": j.pages_found,
        "pages_done": j.pages_done, "error_log": j.error_log,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    }


# --- Site ---
class SQLiteSiteRepo(BaseSiteRepo):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> dict:
        site = Site(**data)
        self.db.add(site)
        await self.db.commit()
        await self.db.refresh(site)
        return _site_to_dict(site)

    async def get_by_id(self, site_id: str) -> Optional[dict]:
        site = await self.db.get(Site, site_id)
        return _site_to_dict(site) if site else None

    async def get_by_token(self, token: str) -> Optional[dict]:
        result = await self.db.execute(select(Site).where(Site.token == token))
        site = result.scalar_one_or_none()
        return _site_to_dict(site) if site else None

    async def list_all(self) -> list[dict]:
        result = await self.db.execute(select(Site).order_by(Site.created_at.desc()))
        return [_site_to_dict(s) for s in result.scalars().all()]

    async def update(self, site_id: str, data: dict) -> Optional[dict]:
        site = await self.db.get(Site, site_id)
        if not site:
            return None
        for k, v in data.items():
            if v is not None:
                setattr(site, k, v)
        await self.db.commit()
        await self.db.refresh(site)
        return _site_to_dict(site)

    async def delete(self, site_id: str) -> bool:
        site = await self.db.get(Site, site_id)
        if not site:
            return False
        await self.db.delete(site)
        await self.db.commit()
        return True


# --- Knowledge ---
class SQLiteKnowledgeRepo(BaseKnowledgeRepo):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> dict:
        chunk = KnowledgeChunk(**data)
        self.db.add(chunk)
        await self.db.commit()
        return _chunk_to_dict(chunk)

    async def get_by_id(self, chunk_id: str) -> Optional[dict]:
        chunk = await self.db.get(KnowledgeChunk, chunk_id)
        return _chunk_to_dict(chunk) if chunk else None

    async def list_by_site(self, site_id: str, page: int = 1, per_page: int = 20) -> dict:
        offset = (page - 1) * per_page
        result = await self.db.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.site_id == site_id)
            .order_by(KnowledgeChunk.crawled_at.desc()).offset(offset).limit(per_page)
        )
        chunks = [_chunk_to_dict(c) for c in result.scalars().all()]
        count_result = await self.db.execute(
            select(func.count()).where(KnowledgeChunk.site_id == site_id)
        )
        total = count_result.scalar()
        return {"chunks": chunks, "total": total, "page": page, "per_page": per_page}

    async def delete(self, chunk_id: str) -> bool:
        chunk = await self.db.get(KnowledgeChunk, chunk_id)
        if not chunk:
            return False
        await self.db.delete(chunk)
        await self.db.commit()
        return True

    async def create_many(self, chunks: list[dict]) -> list[str]:
        ids = []
        for data in chunks:
            chunk = KnowledgeChunk(**data)
            self.db.add(chunk)
            ids.append(data.get("id", chunk.id))
        await self.db.commit()
        return ids


# --- Tool ---
class SQLiteToolRepo(BaseToolRepo):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> dict:
        tool = Tool(**data)
        self.db.add(tool)
        await self.db.commit()
        await self.db.refresh(tool)
        return _tool_to_dict(tool)

    async def get_by_id(self, tool_id: str) -> Optional[dict]:
        tool = await self.db.get(Tool, tool_id)
        return _tool_to_dict(tool) if tool else None

    async def list_by_site(self, site_id: str) -> list[dict]:
        result = await self.db.execute(
            select(Tool).where(Tool.site_id == site_id).order_by(Tool.created_at.desc())
        )
        return [_tool_to_dict(t) for t in result.scalars().all()]

    async def list_enabled_by_site(self, site_id: str) -> list[dict]:
        result = await self.db.execute(
            select(Tool).where(Tool.site_id == site_id, Tool.enabled == True)
        )
        return [_tool_to_dict(t) for t in result.scalars().all()]

    async def update(self, tool_id: str, data: dict) -> Optional[dict]:
        tool = await self.db.get(Tool, tool_id)
        if not tool:
            return None
        for k, v in data.items():
            if v is not None:
                setattr(tool, k, v)
        await self.db.commit()
        return _tool_to_dict(tool)

    async def delete(self, tool_id: str) -> bool:
        tool = await self.db.get(Tool, tool_id)
        if not tool:
            return False
        await self.db.delete(tool)
        await self.db.commit()
        return True


# --- Chat Session ---
class SQLiteChatSessionRepo(BaseChatSessionRepo):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> dict:
        session = ChatSession(**data)
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return _session_to_dict(session)

    async def get_by_id(self, session_id: str) -> Optional[dict]:
        session = await self.db.get(ChatSession, session_id)
        return _session_to_dict(session) if session else None

    async def list_by_site(self, site_id: str, page: int = 1, per_page: int = 20) -> list[dict]:
        offset = (page - 1) * per_page
        result = await self.db.execute(
            select(ChatSession).where(ChatSession.site_id == site_id)
            .order_by(ChatSession.started_at.desc()).offset(offset).limit(per_page)
        )
        return [_session_to_dict(s) for s in result.scalars().all()]

    async def update_messages(self, session_id: str, messages: list[dict]) -> bool:
        session = await self.db.get(ChatSession, session_id)
        if not session:
            return False
        session.messages = messages
        await self.db.commit()
        return True

    async def set_ended(self, session_id: str) -> bool:
        session = await self.db.get(ChatSession, session_id)
        if not session:
            return False
        session.ended_at = datetime.utcnow()
        await self.db.commit()
        return True


# --- Crawl Job ---
class SQLiteCrawlJobRepo(BaseCrawlJobRepo):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> dict:
        job = CrawlJob(**data)
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return _job_to_dict(job)

    async def get_by_id(self, job_id: str) -> Optional[dict]:
        job = await self.db.get(CrawlJob, job_id)
        return _job_to_dict(job) if job else None

    async def list_by_site(self, site_id: str) -> list[dict]:
        result = await self.db.execute(
            select(CrawlJob).where(CrawlJob.site_id == site_id)
            .order_by(CrawlJob.started_at.desc())
        )
        return [_job_to_dict(j) for j in result.scalars().all()]

    async def update(self, job_id: str, data: dict) -> bool:
        job = await self.db.get(CrawlJob, job_id)
        if not job:
            return False
        for k, v in data.items():
            setattr(job, k, v)
        await self.db.commit()
        return True
