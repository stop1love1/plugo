"""MongoDB implementation using Motor (async driver)."""

import uuid
from datetime import datetime
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base import (
    BaseSiteRepo, BaseKnowledgeRepo, BaseToolRepo,
    BaseChatSessionRepo, BaseCrawlJobRepo, BaseUserRepo,
)


def _clean_doc(doc: dict) -> dict:
    """Convert MongoDB _id to id and remove _id."""
    if doc and "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    # Convert datetime to ISO strings for consistency
    for key in ("created_at", "updated_at", "crawled_at", "started_at", "finished_at", "ended_at", "last_crawled_at"):
        if key in doc and isinstance(doc[key], datetime):
            doc[key] = doc[key].isoformat()
    return doc


# --- Site ---
class MongoSiteRepo(BaseSiteRepo):
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["sites"]

    async def create(self, data: dict) -> dict:
        doc = {
            "_id": data.get("id", str(uuid.uuid4())),
            "name": data["name"],
            "url": data["url"],
            "token": data.get("token", uuid.uuid4().hex),
            "llm_provider": data.get("llm_provider", "claude"),
            "llm_model": data.get("llm_model", "claude-sonnet-4-20250514"),
            "primary_color": data.get("primary_color", "#6366f1"),
            "greeting": data.get("greeting", "Xin chào! Tôi có thể giúp gì cho bạn?"),
            "position": data.get("position", "bottom-right"),
            "allowed_domains": data.get("allowed_domains", ""),
            # Crawl management
            "crawl_enabled": data.get("crawl_enabled", False),
            "crawl_auto_interval": data.get("crawl_auto_interval", 0),
            "crawl_max_pages": data.get("crawl_max_pages", 50),
            "crawl_status": data.get("crawl_status", "idle"),
            "last_crawled_at": None,
            "knowledge_count": 0,
            # Timestamps
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    async def get_by_id(self, site_id: str) -> Optional[dict]:
        doc = await self.col.find_one({"_id": site_id})
        return _clean_doc(doc) if doc else None

    async def get_by_token(self, token: str) -> Optional[dict]:
        doc = await self.col.find_one({"token": token})
        return _clean_doc(doc) if doc else None

    async def list_all(self) -> list[dict]:
        cursor = self.col.find().sort("created_at", -1)
        return [_clean_doc(doc) async for doc in cursor]

    async def update(self, site_id: str, data: dict) -> Optional[dict]:
        update_data = {k: v for k, v in data.items() if v is not None}
        update_data["updated_at"] = datetime.utcnow()
        result = await self.col.find_one_and_update(
            {"_id": site_id},
            {"$set": update_data},
            return_document=True,
        )
        return _clean_doc(result) if result else None

    async def delete(self, site_id: str) -> bool:
        result = await self.col.delete_one({"_id": site_id})
        return result.deleted_count > 0


# --- Knowledge ---
class MongoKnowledgeRepo(BaseKnowledgeRepo):
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["knowledge_chunks"]

    async def create(self, data: dict) -> dict:
        doc = {
            "_id": data.get("id", str(uuid.uuid4())),
            "site_id": data["site_id"],
            "source_url": data.get("source_url"),
            "source_type": data.get("source_type", "crawl"),
            "title": data.get("title"),
            "content": data["content"],
            "chunk_index": data.get("chunk_index", 0),
            "embedding_id": data.get("embedding_id"),
            "crawled_at": datetime.utcnow(),
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    async def get_by_id(self, chunk_id: str) -> Optional[dict]:
        doc = await self.col.find_one({"_id": chunk_id})
        return _clean_doc(doc) if doc else None

    async def list_by_site(self, site_id: str, page: int = 1, per_page: int = 20) -> dict:
        skip = (page - 1) * per_page
        cursor = self.col.find({"site_id": site_id}).sort("crawled_at", -1).skip(skip).limit(per_page)
        chunks = [_clean_doc(doc) async for doc in cursor]
        total = await self.col.count_documents({"site_id": site_id})
        return {"chunks": chunks, "total": total, "page": page, "per_page": per_page}

    async def delete(self, chunk_id: str) -> bool:
        result = await self.col.delete_one({"_id": chunk_id})
        return result.deleted_count > 0

    async def create_many(self, chunks: list[dict]) -> list[str]:
        docs = []
        ids = []
        for data in chunks:
            doc_id = data.get("id", str(uuid.uuid4()))
            docs.append({
                "_id": doc_id,
                "site_id": data["site_id"],
                "source_url": data.get("source_url"),
                "source_type": data.get("source_type", "crawl"),
                "title": data.get("title"),
                "content": data["content"],
                "chunk_index": data.get("chunk_index", 0),
                "embedding_id": data.get("embedding_id", doc_id),
                "crawled_at": datetime.utcnow(),
            })
            ids.append(doc_id)
        if docs:
            await self.col.insert_many(docs)
        return ids


# --- Tool ---
class MongoToolRepo(BaseToolRepo):
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["tools"]

    async def create(self, data: dict) -> dict:
        doc = {
            "_id": data.get("id", str(uuid.uuid4())),
            "site_id": data["site_id"],
            "name": data["name"],
            "description": data["description"],
            "method": data.get("method", "GET"),
            "url": data["url"],
            "params_schema": data.get("params_schema", {}),
            "headers": data.get("headers", {}),
            "auth_type": data.get("auth_type"),
            "auth_value": data.get("auth_value"),
            "enabled": data.get("enabled", True),
            "created_at": datetime.utcnow(),
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    async def get_by_id(self, tool_id: str) -> Optional[dict]:
        doc = await self.col.find_one({"_id": tool_id})
        return _clean_doc(doc) if doc else None

    async def list_by_site(self, site_id: str) -> list[dict]:
        cursor = self.col.find({"site_id": site_id}).sort("created_at", -1)
        return [_clean_doc(doc) async for doc in cursor]

    async def list_enabled_by_site(self, site_id: str) -> list[dict]:
        cursor = self.col.find({"site_id": site_id, "enabled": True})
        return [_clean_doc(doc) async for doc in cursor]

    async def update(self, tool_id: str, data: dict) -> Optional[dict]:
        update_data = {k: v for k, v in data.items() if v is not None}
        result = await self.col.find_one_and_update(
            {"_id": tool_id}, {"$set": update_data}, return_document=True,
        )
        return _clean_doc(result) if result else None

    async def delete(self, tool_id: str) -> bool:
        result = await self.col.delete_one({"_id": tool_id})
        return result.deleted_count > 0


# --- Chat Session ---
class MongoChatSessionRepo(BaseChatSessionRepo):
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["chat_sessions"]

    async def create(self, data: dict) -> dict:
        doc = {
            "_id": data.get("id", str(uuid.uuid4())),
            "site_id": data["site_id"],
            "visitor_id": data.get("visitor_id"),
            "page_url": data.get("page_url"),
            "messages": data.get("messages", []),
            "started_at": datetime.utcnow(),
            "ended_at": None,
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    async def get_by_id(self, session_id: str) -> Optional[dict]:
        doc = await self.col.find_one({"_id": session_id})
        if doc:
            doc["message_count"] = len(doc.get("messages", []))
            return _clean_doc(doc)
        return None

    async def list_by_site(self, site_id: str, page: int = 1, per_page: int = 20) -> list[dict]:
        skip = (page - 1) * per_page
        cursor = self.col.find({"site_id": site_id}).sort("started_at", -1).skip(skip).limit(per_page)
        results = []
        async for doc in cursor:
            doc["message_count"] = len(doc.get("messages", []))
            results.append(_clean_doc(doc))
        return results

    async def update_messages(self, session_id: str, messages: list[dict]) -> bool:
        result = await self.col.update_one(
            {"_id": session_id}, {"$set": {"messages": messages}}
        )
        return result.modified_count > 0

    async def set_ended(self, session_id: str) -> bool:
        result = await self.col.update_one(
            {"_id": session_id}, {"$set": {"ended_at": datetime.utcnow()}}
        )
        return result.modified_count > 0


# --- Crawl Job ---
class MongoCrawlJobRepo(BaseCrawlJobRepo):
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["crawl_jobs"]

    async def create(self, data: dict) -> dict:
        doc = {
            "_id": data.get("id", str(uuid.uuid4())),
            "site_id": data["site_id"],
            "status": "pending",
            "start_url": data["start_url"],
            "pages_found": 0,
            "pages_done": 0,
            "error_log": None,
            "started_at": datetime.utcnow(),
            "finished_at": None,
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    async def get_by_id(self, job_id: str) -> Optional[dict]:
        doc = await self.col.find_one({"_id": job_id})
        return _clean_doc(doc) if doc else None

    async def list_by_site(self, site_id: str) -> list[dict]:
        cursor = self.col.find({"site_id": site_id}).sort("started_at", -1)
        return [_clean_doc(doc) async for doc in cursor]

    async def update(self, job_id: str, data: dict) -> bool:
        result = await self.col.update_one({"_id": job_id}, {"$set": data})
        return result.modified_count > 0


# --- User ---
class MongoUserRepo(BaseUserRepo):
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["users"]

    async def create(self, data: dict) -> dict:
        doc = {
            "_id": data.get("id", str(uuid.uuid4())),
            "username": data["username"],
            "password_hash": data["password_hash"],
            "role": data.get("role", "admin"),
            "created_at": datetime.utcnow(),
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    async def get_by_id(self, user_id: str) -> Optional[dict]:
        doc = await self.col.find_one({"_id": user_id})
        return _clean_doc(doc) if doc else None

    async def get_by_username(self, username: str) -> Optional[dict]:
        doc = await self.col.find_one({"username": username})
        return _clean_doc(doc) if doc else None

    async def count(self) -> int:
        return await self.col.count_documents({})
