import contextlib

from config import settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add new columns if they don't exist (lightweight migration)
        await _migrate_add_columns(conn)


async def _migrate_add_columns(conn):
    """Add missing columns and indexes to existing tables (idempotent)."""
    import sqlalchemy as sa

    # --- Composite indexes on knowledge_chunks ---
    # Added to speed up hot paths (list_crawled_urls, list_by_url, create_many dedup,
    # list_content_hashes) that previously did full table scans at scale.
    index_migrations = [
        "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_site_url "
        "ON knowledge_chunks (site_id, source_url)",
        "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_site_hash "
        "ON knowledge_chunks (site_id, content_hash)",
    ]
    for stmt in index_migrations:
        with contextlib.suppress(Exception):  # Index may already exist / table missing in legacy test DBs
            await conn.execute(sa.text(stmt))

    migrations = [
        ("sites", "system_prompt", "TEXT DEFAULT ''"),
        ("sites", "bot_rules", "TEXT DEFAULT ''"),
        ("sites", "bot_avatar", "VARCHAR(10) DEFAULT ''"),
        ("sites", "header_subtitle", "VARCHAR(100) DEFAULT ''"),
        ("sites", "input_placeholder", "VARCHAR(200) DEFAULT ''"),
        ("sites", "auto_open_delay", "INTEGER DEFAULT 0"),
        ("sites", "bubble_size", "VARCHAR(10) DEFAULT 'medium'"),
        ("sites", "crawl_max_depth", "INTEGER DEFAULT 0"),
        ("sites", "crawl_exclude_patterns", "TEXT DEFAULT ''"),
        ("sites", "response_language", "VARCHAR(10) DEFAULT 'auto'"),
        # Authenticated crawl (Playwright browser login)
        ("sites", "crawl_use_browser", "BOOLEAN DEFAULT 0"),
        ("sites", "crawl_login_url", "VARCHAR(2048)"),
        ("sites", "crawl_login_username_selector", "VARCHAR(500) DEFAULT 'input[name=''email''], input[name=''username''], input[type=''email'']'"),
        ("sites", "crawl_login_password_selector", "VARCHAR(500) DEFAULT 'input[name=''password''], input[type=''password'']'"),
        ("sites", "crawl_login_submit_selector", "VARCHAR(500) DEFAULT 'button[type=''submit''], input[type=''submit'']'"),
        ("sites", "crawl_login_username", "VARCHAR(500)"),
        ("sites", "crawl_login_password", "VARCHAR(500)"),
        ("sites", "crawl_login_success_url", "VARCHAR(2048)"),
        # Per-site SSRF override for local dev / on-prem wikis
        ("sites", "allow_private_urls", "BOOLEAN DEFAULT 0"),
        # Per-session token usage + cost tracking
        ("chat_sessions", "tokens_input", "INTEGER DEFAULT 0"),
        ("chat_sessions", "tokens_output", "INTEGER DEFAULT 0"),
        ("chat_sessions", "cost_usd", "REAL DEFAULT 0.0"),
    ]
    for table, column, col_type in migrations:
        with contextlib.suppress(Exception):  # Column may already exist
            await conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
