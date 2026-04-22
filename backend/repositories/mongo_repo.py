"""MongoDB implementation using Motor (async driver)."""

import uuid
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base import (
    BaseAuditLogRepo,
    BaseChatSessionRepo,
    BaseConversationSummaryRepo,
    BaseCrawlJobRepo,
    BaseFlowRepo,
    BaseFlowStepRepo,
    BaseKnowledgeRepo,
    BaseLLMKeyRepo,
    BaseSiteRepo,
    BaseToolRepo,
    BaseUserRepo,
    BaseVisitorMemoryRepo,
)


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create indexes on frequently queried fields to avoid full collection scans."""
    # sites: unique on token, index on domain
    await db["sites"].create_index("token", unique=True)
    await db["sites"].create_index("domain")

    # knowledge_chunks: index on site_id + composites for hot paths
    # (list_crawled_urls/list_by_url scan by site_id+source_url; create_many
    # dedup + list_content_hashes filter on site_id+content_hash).
    await db["knowledge_chunks"].create_index("site_id")
    await db["knowledge_chunks"].create_index([("site_id", 1), ("source_url", 1)])
    await db["knowledge_chunks"].create_index([("site_id", 1), ("content_hash", 1)])

    # tools: index on site_id
    await db["tools"].create_index("site_id")

    # chat_sessions: index on site_id, compound on (visitor_id, site_id)
    await db["chat_sessions"].create_index("site_id")
    await db["chat_sessions"].create_index([("visitor_id", 1), ("site_id", 1)])

    # visitor_memories: compound on (visitor_id, site_id)
    await db["visitor_memories"].create_index([("visitor_id", 1), ("site_id", 1)])

    # crawl_jobs: index on site_id
    await db["crawl_jobs"].create_index("site_id")


def _clean_doc(doc: dict) -> dict:
    """Convert MongoDB _id to id and remove _id."""
    doc = dict(doc)  # work on a copy to avoid mutating the caller's dict
    if doc and "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    # Convert datetime to ISO strings for consistency
    for key in ("created_at", "updated_at", "crawled_at", "started_at", "finished_at", "ended_at", "last_crawled_at"):
        if key in doc and isinstance(doc[key], datetime):
            doc[key] = doc[key].isoformat()
    # Mask crawl_login_password the same way SQLite does
    if "crawl_login_password" in doc:
        doc["crawl_login_password"] = "********" if doc["crawl_login_password"] else ""
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
            "greeting": data.get("greeting", "Hello! How can I help you?"),
            "position": data.get("position", "bottom-right"),
            "widget_title": data.get("widget_title", ""),
            "dark_mode": data.get("dark_mode", "auto"),
            "show_branding": data.get("show_branding", True),
            "bot_avatar": data.get("bot_avatar", ""),
            "header_subtitle": data.get("header_subtitle", ""),
            "input_placeholder": data.get("input_placeholder", ""),
            "auto_open_delay": data.get("auto_open_delay", 0),
            "bubble_size": data.get("bubble_size", "medium"),
            "allowed_domains": data.get("allowed_domains", ""),
            "suggestions": data.get("suggestions", []),
            "is_approved": data.get("is_approved", False),
            "system_prompt": data.get("system_prompt", ""),
            "bot_rules": data.get("bot_rules", ""),
            "response_language": data.get("response_language", "auto"),
            # Crawl management
            "crawl_enabled": data.get("crawl_enabled", False),
            "crawl_auto_interval": data.get("crawl_auto_interval", 0),
            "crawl_max_pages": data.get("crawl_max_pages", 50),
            "crawl_max_depth": data.get("crawl_max_depth", 0),
            "crawl_exclude_patterns": data.get("crawl_exclude_patterns", ""),
            "crawl_status": data.get("crawl_status", "idle"),
            "last_crawled_at": None,
            "knowledge_count": 0,
            # Authenticated crawl
            "crawl_use_browser": data.get("crawl_use_browser", False),
            "crawl_login_url": data.get("crawl_login_url", ""),
            "crawl_login_username_selector": data.get("crawl_login_username_selector", ""),
            "crawl_login_password_selector": data.get("crawl_login_password_selector", ""),
            "crawl_login_submit_selector": data.get("crawl_login_submit_selector", ""),
            "crawl_login_username": data.get("crawl_login_username", ""),
            "crawl_login_password": data.get("crawl_login_password", ""),
            "crawl_login_success_url": data.get("crawl_login_success_url", ""),
            "allow_private_urls": bool(data.get("allow_private_urls", False)),
            # Timestamps
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    async def get_by_id(self, site_id: str) -> dict | None:
        doc = await self.col.find_one({"_id": site_id})
        return _clean_doc(doc) if doc else None

    async def get_by_token(self, token: str) -> dict | None:
        doc = await self.col.find_one({"token": token})
        return _clean_doc(doc) if doc else None

    async def list_all(self) -> list[dict]:
        cursor = self.col.find().sort("created_at", -1)
        return [_clean_doc(doc) async for doc in cursor]

    async def update(self, site_id: str, data: dict) -> dict | None:
        update_data = {k: v for k, v in data.items() if v is not None}
        update_data["updated_at"] = datetime.now(UTC)
        result = await self.col.find_one_and_update(
            {"_id": site_id},
            {"$set": update_data},
            return_document=True,
        )
        return _clean_doc(result) if result else None

    async def delete(self, site_id: str) -> bool:
        result = await self.col.delete_one({"_id": site_id})
        return result.deleted_count > 0

    async def get_crawl_password(self, site_id: str) -> str | None:
        doc = await self.col.find_one({"_id": site_id}, {"crawl_login_password": 1})
        if not doc or not doc.get("crawl_login_password"):
            return None
        from utils.crypto import decrypt_value
        return decrypt_value(doc["crawl_login_password"])


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
            "content_hash": data.get("content_hash", ""),
            "chunk_index": data.get("chunk_index", 0),
            "embedding_id": data.get("embedding_id"),
            "crawled_at": datetime.now(UTC),
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    async def get_by_id(self, chunk_id: str) -> dict | None:
        doc = await self.col.find_one({"_id": chunk_id})
        return _clean_doc(doc) if doc else None

    async def list_by_site(self, site_id: str, page: int = 1, per_page: int = 20, search: str | None = None) -> dict:
        skip = (page - 1) * per_page
        query: dict = {"site_id": site_id}
        if search:
            query["$or"] = [
                {"title": {"$regex": search, "$options": "i"}},
                {"content": {"$regex": search, "$options": "i"}},
                {"source_url": {"$regex": search, "$options": "i"}},
            ]
        cursor = self.col.find(query).sort("crawled_at", -1).skip(skip).limit(per_page)
        chunks = [_clean_doc(doc) async for doc in cursor]
        total = await self.col.count_documents(query)
        return {"chunks": chunks, "total": total, "page": page, "per_page": per_page}

    async def update(self, chunk_id: str, data: dict) -> dict | None:
        result = await self.col.find_one_and_update(
            {"_id": chunk_id},
            {"$set": data},
            return_document=True,
        )
        return _clean_doc(result) if result else None

    async def delete(self, chunk_id: str) -> bool:
        result = await self.col.delete_one({"_id": chunk_id})
        return result.deleted_count > 0

    async def create_many(self, chunks: list[dict]) -> list[str]:
        if not chunks:
            return []

        # Batch dedup: get all existing hashes for this site in one query
        hashes_to_check = [c.get("content_hash") for c in chunks if c.get("content_hash")]
        existing_hashes: set[str] = set()
        if hashes_to_check:
            cursor = self.col.find(
                {"site_id": chunks[0]["site_id"], "content_hash": {"$in": hashes_to_check}},
                {"content_hash": 1},
            )
            existing_hashes = {doc["content_hash"] async for doc in cursor}

        docs = []
        ids = []
        for data in chunks:
            content_hash = data.get("content_hash")
            if content_hash and content_hash in existing_hashes:
                continue  # Duplicate — skip

            doc_id = data.get("id", str(uuid.uuid4()))
            docs.append({
                "_id": doc_id,
                "site_id": data["site_id"],
                "source_url": data.get("source_url"),
                "source_type": data.get("source_type", "crawl"),
                "title": data.get("title"),
                "content": data["content"],
                "content_hash": content_hash,
                "chunk_index": data.get("chunk_index", 0),
                "embedding_id": data.get("embedding_id", doc_id),
                "crawled_at": datetime.now(UTC),
            })
            ids.append(doc_id)
        if docs:
            await self.col.insert_many(docs)
        return ids

    async def delete_many(self, chunk_ids: list[str]) -> int:
        if not chunk_ids:
            return 0
        result = await self.col.delete_many({"_id": {"$in": chunk_ids}})
        return result.deleted_count

    async def get_many(self, chunk_ids: list[str]) -> list[dict]:
        if not chunk_ids:
            return []
        cursor = self.col.find({"_id": {"$in": chunk_ids}})
        return [_clean_doc(doc) async for doc in cursor]

    async def list_crawled_urls(self, site_id: str) -> list[dict]:
        pipeline = [
            {"$match": {"site_id": site_id, "source_url": {"$ne": None}}},
            {"$group": {
                "_id": "$source_url",
                "chunk_count": {"$sum": 1},
                "title": {"$max": "$title"},
                "last_crawled_at": {"$max": "$crawled_at"},
                "source_type": {"$min": "$source_type"},
            }},
            {"$sort": {"last_crawled_at": -1}},
            {"$project": {
                "_id": 0,
                "source_url": "$_id",
                "chunk_count": 1,
                "title": 1,
                "last_crawled_at": 1,
                "source_type": 1,
            }},
        ]
        results = []
        async for doc in self.col.aggregate(pipeline):
            if "last_crawled_at" in doc and isinstance(doc["last_crawled_at"], datetime):
                doc["last_crawled_at"] = doc["last_crawled_at"].isoformat()
            results.append(doc)
        return results

    async def list_content_hashes(self, site_id: str) -> set[str]:
        """Return all content hashes for a site (for deduplication)."""
        cursor = self.col.find(
            {"site_id": site_id, "content_hash": {"$ne": None}},
            {"content_hash": 1, "_id": 0},
        )
        return {doc["content_hash"] async for doc in cursor if doc.get("content_hash")}

    async def list_by_url(self, site_id: str, source_url: str) -> list[dict]:
        cursor = self.col.find(
            {"site_id": site_id, "source_url": source_url}
        ).sort("chunk_index", 1)
        return [_clean_doc(doc) async for doc in cursor]

    async def delete_by_url(self, site_id: str, source_url: str) -> int:
        result = await self.col.delete_many({"site_id": site_id, "source_url": source_url})
        return result.deleted_count

    async def delete_all_by_site(self, site_id: str) -> int:
        result = await self.col.delete_many({"site_id": site_id})
        return result.deleted_count


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
            "created_at": datetime.now(UTC),
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    async def get_by_id(self, tool_id: str) -> dict | None:
        doc = await self.col.find_one({"_id": tool_id})
        return _clean_doc(doc) if doc else None

    async def list_by_site(self, site_id: str) -> list[dict]:
        cursor = self.col.find({"site_id": site_id}).sort("created_at", -1)
        return [_clean_doc(doc) async for doc in cursor]

    async def list_enabled_by_site(self, site_id: str) -> list[dict]:
        cursor = self.col.find({"site_id": site_id, "enabled": True})
        return [_clean_doc(doc) async for doc in cursor]

    async def update(self, tool_id: str, data: dict) -> dict | None:
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
            "started_at": datetime.now(UTC),
            "ended_at": None,
            "tokens_input": 0,
            "tokens_output": 0,
            "cost_usd": 0.0,
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    @staticmethod
    def _enrich_session(doc: dict) -> dict:
        messages = doc.get("messages", [])
        doc["message_count"] = len(messages)
        first_msg = ""
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "user":
                first_msg = (msg.get("content") or "")[:200]
                break
        doc["first_message"] = first_msg
        # Ensure token/cost keys are present for older docs that pre-date the feature.
        doc.setdefault("tokens_input", 0)
        doc.setdefault("tokens_output", 0)
        doc.setdefault("cost_usd", 0.0)
        return doc

    async def get_by_id(self, session_id: str) -> dict | None:
        doc = await self.col.find_one({"_id": session_id})
        if doc:
            self._enrich_session(doc)
            return _clean_doc(doc)
        return None

    async def list_by_site(self, site_id: str, page: int = 1, per_page: int = 20) -> list[dict]:
        skip = (page - 1) * per_page
        cursor = self.col.find({"site_id": site_id}).sort("started_at", -1).skip(skip).limit(per_page)
        results = []
        async for doc in cursor:
            self._enrich_session(doc)
            results.append(_clean_doc(doc))
        return results

    async def list_by_site_since(self, site_id: str, since: datetime) -> list[dict]:
        cursor = self.col.find({
            "site_id": site_id,
            "started_at": {"$gte": since},
        }).sort("started_at", -1)
        results = []
        async for doc in cursor:
            self._enrich_session(doc)
            results.append(_clean_doc(doc))
        return results

    async def update_messages(self, session_id: str, messages: list[dict]) -> bool:
        # matched_count (not modified_count): True means session exists.
        # modified_count would return False when the new messages equal the stored value,
        # diverging from the SQLite path that always returns True on found session.
        result = await self.col.update_one(
            {"_id": session_id}, {"$set": {"messages": messages}}
        )
        return result.matched_count > 0

    async def set_ended(self, session_id: str, clear: bool = False) -> bool:
        update = {"$set": {"ended_at": None}} if clear else {"$set": {"ended_at": datetime.now(UTC)}}
        result = await self.col.update_one({"_id": session_id}, update)
        return result.matched_count > 0

    async def aggregate_overview(self, site_id: str, since: datetime) -> dict:
        """Single-pipeline aggregation — no per-session Python iteration."""
        pipeline = [
            {"$match": {"site_id": site_id, "started_at": {"$gte": since}}},
            {"$group": {
                "_id": None,
                "total_sessions": {"$sum": 1},
                "total_messages": {"$sum": {"$size": {"$ifNull": ["$messages", []]}}},
                "avg_duration": {
                    "$avg": {
                        "$cond": [
                            {"$ifNull": ["$ended_at", False]},
                            {"$divide": [
                                {"$subtract": ["$ended_at", "$started_at"]},
                                1000,  # ms → seconds
                            ]},
                            None,
                        ]
                    }
                },
            }},
        ]
        async for doc in self.col.aggregate(pipeline):
            return {
                "total_sessions": int(doc.get("total_sessions") or 0),
                "total_messages": int(doc.get("total_messages") or 0),
                "avg_session_duration_seconds": float(doc.get("avg_duration") or 0.0),
            }
        return {"total_sessions": 0, "total_messages": 0, "avg_session_duration_seconds": 0.0}

    async def add_token_usage(
        self, session_id: str, in_tokens: int, out_tokens: int, cost_usd: float
    ) -> bool:
        # matched_count so a zero-delta call (still a meaningful "session exists"
        # signal) doesn't disagree with SQLite's rowcount>0 semantics.
        result = await self.col.update_one(
            {"_id": session_id},
            {"$inc": {
                "tokens_input": int(in_tokens),
                "tokens_output": int(out_tokens),
                "cost_usd": float(cost_usd),
            }},
        )
        return result.matched_count > 0


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
            "pages_skipped": 0,
            "pages_failed": 0,
            "chunks_created": 0,
            "current_url": None,
            "error_log": None,
            "crawl_log": None,
            "started_at": datetime.now(UTC),
            "finished_at": None,
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    async def get_by_id(self, job_id: str) -> dict | None:
        doc = await self.col.find_one({"_id": job_id})
        return _clean_doc(doc) if doc else None

    async def list_by_site(self, site_id: str) -> list[dict]:
        cursor = self.col.find({"site_id": site_id}).sort("started_at", -1)
        return [_clean_doc(doc) async for doc in cursor]

    async def update(self, job_id: str, data: dict) -> bool:
        # matched_count so a no-op update still reports "job exists" like SQLite does.
        result = await self.col.update_one({"_id": job_id}, {"$set": data})
        return result.matched_count > 0


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
            "created_at": datetime.now(UTC),
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    async def get_by_id(self, user_id: str) -> dict | None:
        doc = await self.col.find_one({"_id": user_id})
        return _clean_doc(doc) if doc else None

    async def get_by_username(self, username: str) -> dict | None:
        doc = await self.col.find_one({"username": username})
        return _clean_doc(doc) if doc else None

    async def count(self) -> int:
        return await self.col.count_documents({})

    async def list_all(self) -> list[dict]:
        cursor = self.col.find().sort("created_at", -1)
        users = []
        async for doc in cursor:
            created_at = doc.get("created_at")
            users.append({"id": doc["_id"], "username": doc["username"], "role": doc.get("role", "admin"), "created_at": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at) if created_at else None})
        return users

    async def update_role(self, user_id: str, role: str) -> dict | None:
        result = await self.col.find_one_and_update(
            {"_id": user_id}, {"$set": {"role": role}}, return_document=True
        )
        if not result:
            return None
        created_at = result.get("created_at")
        return {"id": result["_id"], "username": result["username"], "role": result.get("role", "admin"), "created_at": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at) if created_at else None}

    async def delete(self, user_id: str) -> bool:
        result = await self.col.delete_one({"_id": user_id})
        return result.deleted_count > 0


# --- Visitor Memory ---
class MongoVisitorMemoryRepo(BaseVisitorMemoryRepo):
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["visitor_memories"]

    async def create(self, data: dict) -> dict:
        doc = {
            "_id": data.get("id", str(uuid.uuid4())),
            "visitor_id": data["visitor_id"],
            "site_id": data["site_id"],
            "category": data.get("category", "context"),
            "key": data["key"],
            "value": data["value"],
            "confidence": data.get("confidence", "medium"),
            "source_session_id": data.get("source_session_id"),
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    async def get_by_id(self, memory_id: str) -> dict | None:
        doc = await self.col.find_one({"_id": memory_id})
        return _clean_doc(doc) if doc else None

    async def list_by_visitor(self, visitor_id: str, site_id: str) -> list[dict]:
        cursor = self.col.find(
            {"visitor_id": visitor_id, "site_id": site_id}
        ).sort("updated_at", -1)
        return [_clean_doc(doc) async for doc in cursor]

    async def upsert(self, visitor_id: str, site_id: str, key: str, data: dict) -> dict:
        filter_query = {"visitor_id": visitor_id, "site_id": site_id, "key": key}
        existing = await self.col.find_one(filter_query)
        if existing:
            update_data = {k: v for k, v in data.items() if v is not None}
            update_data["updated_at"] = datetime.now(UTC)
            result = await self.col.find_one_and_update(
                filter_query, {"$set": update_data}, return_document=True,
            )
            return _clean_doc(result)
        else:
            doc = {
                "_id": data.get("id", str(uuid.uuid4())),
                "visitor_id": visitor_id,
                "site_id": site_id,
                "category": data.get("category", "context"),
                "key": key,
                "value": data.get("value", ""),
                "confidence": data.get("confidence", "medium"),
                "source_session_id": data.get("source_session_id"),
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
            await self.col.insert_one(doc)
            return _clean_doc(doc)

    async def delete(self, memory_id: str) -> bool:
        result = await self.col.delete_one({"_id": memory_id})
        return result.deleted_count > 0

    async def delete_by_visitor(self, visitor_id: str, site_id: str) -> int:
        result = await self.col.delete_many({"visitor_id": visitor_id, "site_id": site_id})
        return result.deleted_count

    async def list_by_site(self, site_id: str) -> list[dict]:
        cursor = self.col.find({"site_id": site_id}).sort("updated_at", -1)
        return [_clean_doc(doc) async for doc in cursor]


# --- Conversation Summary ---
class MongoConversationSummaryRepo(BaseConversationSummaryRepo):
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["conversation_summaries"]

    async def create(self, data: dict) -> dict:
        doc = {
            "_id": data.get("id", str(uuid.uuid4())),
            "session_id": data["session_id"],
            "site_id": data["site_id"],
            "summary_text": data["summary_text"],
            "message_count_summarized": data.get("message_count_summarized", 0),
            "total_message_count": data.get("total_message_count", 0),
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    async def get_by_session(self, session_id: str) -> dict | None:
        doc = await self.col.find_one({"session_id": session_id})
        return _clean_doc(doc) if doc else None

    async def upsert_by_session(self, session_id: str, data: dict) -> dict:
        existing = await self.col.find_one({"session_id": session_id})
        if existing:
            update_data = {k: v for k, v in data.items() if v is not None}
            update_data["updated_at"] = datetime.now(UTC)
            result = await self.col.find_one_and_update(
                {"session_id": session_id}, {"$set": update_data}, return_document=True,
            )
            return _clean_doc(result)
        else:
            doc = {
                "_id": data.get("id", str(uuid.uuid4())),
                "session_id": session_id,
                "site_id": data["site_id"],
                "summary_text": data.get("summary_text", ""),
                "message_count_summarized": data.get("message_count_summarized", 0),
                "total_message_count": data.get("total_message_count", 0),
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
            await self.col.insert_one(doc)
            return _clean_doc(doc)

    async def delete(self, summary_id: str) -> bool:
        result = await self.col.delete_one({"_id": summary_id})
        return result.deleted_count > 0


# --- Audit Log ---
class MongoAuditLogRepo(BaseAuditLogRepo):
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["audit_logs"]

    async def create(self, data: dict) -> dict:
        doc = {
            "_id": data.get("id", str(uuid.uuid4())),
            "user_id": data["user_id"],
            "username": data["username"],
            "action": data["action"],
            "resource_type": data["resource_type"],
            "resource_id": data.get("resource_id"),
            "details": data.get("details"),
            "created_at": datetime.now(UTC),
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    async def list_by_site(self, page: int = 1, per_page: int = 50) -> dict:
        skip = (page - 1) * per_page
        cursor = self.col.find().sort("created_at", -1).skip(skip).limit(per_page)
        logs = [_clean_doc(doc) async for doc in cursor]
        total = await self.col.count_documents({})
        return {"logs": logs, "total": total, "page": page, "per_page": per_page}


# --- LLM Key ---
class MongoLLMKeyRepo(BaseLLMKeyRepo):
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["llm_keys"]

    async def list_all(self) -> list[dict]:
        cursor = self.col.find()
        return [_clean_doc(doc) async for doc in cursor]

    async def get_by_provider(self, provider: str) -> dict | None:
        doc = await self.col.find_one({"provider": provider})
        return _clean_doc(doc) if doc else None

    async def upsert(self, provider: str, data: dict) -> dict:
        existing = await self.col.find_one({"provider": provider})
        if existing:
            update_data = {k: v for k, v in data.items() if v is not None}
            update_data["updated_at"] = datetime.now(UTC)
            result = await self.col.find_one_and_update(
                {"provider": provider}, {"$set": update_data}, return_document=True,
            )
            return _clean_doc(result)
        else:
            doc = {
                "_id": str(uuid.uuid4()),
                "provider": provider,
                "api_key": data["api_key"],
                "label": data.get("label", ""),
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
            await self.col.insert_one(doc)
            return _clean_doc(doc)

    async def delete_by_provider(self, provider: str) -> bool:
        result = await self.col.delete_one({"provider": provider})
        return result.deleted_count > 0


# --- Flow ---
class MongoFlowRepo(BaseFlowRepo):
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["flows"]
        self._steps_col = db["flow_steps"]

    async def create(self, data: dict) -> dict:
        doc = {
            "_id": data.get("id", str(uuid.uuid4())),
            "site_id": data["site_id"],
            "name": data["name"],
            "description": data.get("description", ""),
            "requires_login": data.get("requires_login", False),
            "is_enabled": data.get("is_enabled", True),
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    async def get_by_id(self, flow_id: str) -> dict | None:
        doc = await self.col.find_one({"_id": flow_id})
        return _clean_doc(doc) if doc else None

    async def list_by_site(self, site_id: str) -> list[dict]:
        cursor = self.col.find({"site_id": site_id}).sort("created_at", -1)
        return [_clean_doc(doc) async for doc in cursor]

    async def update(self, flow_id: str, data: dict) -> dict | None:
        update_data = dict(data)
        update_data["updated_at"] = datetime.now(UTC)
        result = await self.col.find_one_and_update(
            {"_id": flow_id},
            {"$set": update_data},
            return_document=True,
        )
        return _clean_doc(result) if result else None

    async def delete(self, flow_id: str) -> bool:
        # Cascade delete associated flow steps
        await self._steps_col.delete_many({"flow_id": flow_id})
        result = await self.col.delete_one({"_id": flow_id})
        return result.deleted_count > 0

    async def delete_by_site(self, site_id: str) -> int:
        # Cascade delete flow steps for all flows in this site
        cursor = self.col.find({"site_id": site_id}, {"_id": 1})
        flow_ids = [doc["_id"] async for doc in cursor]
        if flow_ids:
            await self._steps_col.delete_many({"flow_id": {"$in": flow_ids}})
        result = await self.col.delete_many({"site_id": site_id})
        return result.deleted_count


# --- Flow Step ---
class MongoFlowStepRepo(BaseFlowStepRepo):
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["flow_steps"]

    async def create(self, data: dict) -> dict:
        doc = {
            "_id": data.get("id", str(uuid.uuid4())),
            "flow_id": data["flow_id"],
            "step_order": data.get("step_order", 1),
            "title": data["title"],
            "description": data.get("description", ""),
            "url": data.get("url"),
            "screenshot_url": data.get("screenshot_url"),
            "created_at": datetime.now(UTC),
        }
        await self.col.insert_one(doc)
        return _clean_doc(doc)

    async def get_by_id(self, step_id: str) -> dict | None:
        doc = await self.col.find_one({"_id": step_id})
        return _clean_doc(doc) if doc else None

    async def list_by_flow(self, flow_id: str) -> list[dict]:
        cursor = self.col.find({"flow_id": flow_id}).sort("step_order", 1)
        return [_clean_doc(doc) async for doc in cursor]

    async def update(self, step_id: str, data: dict) -> dict | None:
        update_data = dict(data)
        result = await self.col.find_one_and_update(
            {"_id": step_id},
            {"$set": update_data},
            return_document=True,
        )
        return _clean_doc(result) if result else None

    async def delete(self, step_id: str) -> bool:
        result = await self.col.delete_one({"_id": step_id})
        return result.deleted_count > 0

    async def delete_by_flow(self, flow_id: str) -> int:
        result = await self.col.delete_many({"flow_id": flow_id})
        return result.deleted_count

    async def reorder(self, flow_id: str, step_ids: list[str]) -> bool:
        for idx, step_id in enumerate(step_ids):
            await self.col.update_one(
                {"_id": step_id, "flow_id": flow_id},
                {"$set": {"step_order": idx + 1}},
            )
        return True
