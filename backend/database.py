from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import settings


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
    """Add missing columns to existing tables (idempotent)."""
    import sqlalchemy as sa

    migrations = [
        ("sites", "system_prompt", "TEXT DEFAULT ''"),
        ("sites", "bot_rules", "TEXT DEFAULT ''"),
    ]
    for table, column, col_type in migrations:
        try:
            await conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        except Exception:
            pass  # Column already exists
