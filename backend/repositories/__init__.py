"""
Database repository factory.

Usage in routes:
    from repositories import get_repos
    repos = await get_repos()
    site = await repos.sites.get_by_id("...")
"""

from repositories.base import (
    BaseSiteRepo, BaseKnowledgeRepo, BaseToolRepo,
    BaseChatSessionRepo, BaseCrawlJobRepo, BaseUserRepo,
    BaseVisitorMemoryRepo, BaseConversationSummaryRepo,
    BaseAuditLogRepo,
)


class Repositories:
    """Container for all repository instances."""
    def __init__(
        self,
        sites: BaseSiteRepo,
        knowledge: BaseKnowledgeRepo,
        tools: BaseToolRepo,
        chat_sessions: BaseChatSessionRepo,
        crawl_jobs: BaseCrawlJobRepo,
        users: BaseUserRepo,
        visitor_memories: BaseVisitorMemoryRepo,
        conversation_summaries: BaseConversationSummaryRepo,
        audit_logs: BaseAuditLogRepo,
    ):
        self.sites = sites
        self.knowledge = knowledge
        self.tools = tools
        self.chat_sessions = chat_sessions
        self.crawl_jobs = crawl_jobs
        self.users = users
        self.visitor_memories = visitor_memories
        self.conversation_summaries = conversation_summaries
        self.audit_logs = audit_logs


# --- MongoDB connection (lazy init) ---
_mongo_client = None
_mongo_db = None


def _get_mongo_db():
    global _mongo_client, _mongo_db
    if _mongo_db is None:
        from motor.motor_asyncio import AsyncIOMotorClient
        from config import settings
        _mongo_client = AsyncIOMotorClient(settings.mongodb_url)
        _mongo_db = _mongo_client[settings.mongodb_database]
    return _mongo_db


# --- SQLite session (lazy init) ---
_sqlite_session_factory = None


def _get_sqlite_session():
    global _sqlite_session_factory
    if _sqlite_session_factory is None:
        from database import async_session
        _sqlite_session_factory = async_session
    return _sqlite_session_factory


async def get_repos() -> Repositories:
    """FastAPI dependency — returns the right repos based on DATABASE_PROVIDER."""
    from config import settings

    if settings.database_provider == "mongodb":
        from repositories.mongo_repo import (
            MongoSiteRepo, MongoKnowledgeRepo, MongoToolRepo,
            MongoChatSessionRepo, MongoCrawlJobRepo, MongoUserRepo,
            MongoVisitorMemoryRepo, MongoConversationSummaryRepo,
            MongoAuditLogRepo,
        )
        db = _get_mongo_db()
        return Repositories(
            sites=MongoSiteRepo(db),
            knowledge=MongoKnowledgeRepo(db),
            tools=MongoToolRepo(db),
            chat_sessions=MongoChatSessionRepo(db),
            crawl_jobs=MongoCrawlJobRepo(db),
            users=MongoUserRepo(db),
            visitor_memories=MongoVisitorMemoryRepo(db),
            conversation_summaries=MongoConversationSummaryRepo(db),
            audit_logs=MongoAuditLogRepo(db),
        )
    else:
        # Default: SQLite
        from repositories.sqlite_repo import (
            SQLiteSiteRepo, SQLiteKnowledgeRepo, SQLiteToolRepo,
            SQLiteChatSessionRepo, SQLiteCrawlJobRepo, SQLiteUserRepo,
            SQLiteVisitorMemoryRepo, SQLiteConversationSummaryRepo,
            SQLiteAuditLogRepo,
        )
        session_factory = _get_sqlite_session()
        db = session_factory()
        return Repositories(
            sites=SQLiteSiteRepo(db),
            knowledge=SQLiteKnowledgeRepo(db),
            tools=SQLiteToolRepo(db),
            chat_sessions=SQLiteChatSessionRepo(db),
            crawl_jobs=SQLiteCrawlJobRepo(db),
            users=SQLiteUserRepo(db),
            visitor_memories=SQLiteVisitorMemoryRepo(db),
            conversation_summaries=SQLiteConversationSummaryRepo(db),
            audit_logs=SQLiteAuditLogRepo(db),
        )


async def close_mongo():
    """Call on shutdown to close MongoDB connection."""
    global _mongo_client
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None
