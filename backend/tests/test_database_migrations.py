"""Regression tests for lightweight SQLite migrations."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from database import _migrate_add_columns


@pytest.mark.asyncio
async def test_migrate_add_columns_adds_missing_site_columns(tmp_path: Path):
    """Older SQLite schemas should be upgraded with new site columns."""
    db_path = tmp_path / "legacy.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE sites (
                    id VARCHAR PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    url VARCHAR(2048) NOT NULL,
                    token VARCHAR(64) NOT NULL,
                    llm_provider VARCHAR(50),
                    llm_model VARCHAR(100),
                    primary_color VARCHAR(7),
                    greeting TEXT,
                    position VARCHAR(20),
                    suggestions JSON,
                    allowed_domains TEXT,
                    crawl_enabled BOOLEAN,
                    crawl_auto_interval INTEGER,
                    crawl_max_pages INTEGER,
                    crawl_status VARCHAR(20),
                    last_crawled_at DATETIME,
                    knowledge_count INTEGER,
                    created_at DATETIME,
                    updated_at DATETIME,
                    is_approved BOOLEAN DEFAULT 0,
                    widget_title VARCHAR(100) DEFAULT '',
                    dark_mode VARCHAR(10) DEFAULT 'auto',
                    show_branding BOOLEAN DEFAULT 1,
                    system_prompt TEXT DEFAULT '',
                    bot_rules TEXT DEFAULT ''
                )
                """
            )
        )

        await _migrate_add_columns(conn)

        columns_result = await conn.execute(text("PRAGMA table_info(sites)"))
        column_names = {row[1] for row in columns_result.fetchall()}

    await engine.dispose()

    assert "bot_avatar" in column_names
    assert "header_subtitle" in column_names
    assert "input_placeholder" in column_names
    assert "auto_open_delay" in column_names
    assert "bubble_size" in column_names
    assert "crawl_max_depth" in column_names
    assert "crawl_exclude_patterns" in column_names


@pytest.mark.asyncio
async def test_migrate_add_columns_adds_chat_session_token_columns(tmp_path: Path):
    """Chat sessions tracked in older DBs must gain token usage + cost columns."""
    db_path = tmp_path / "legacy_chat.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    async with engine.begin() as conn:
        # Legacy chat_sessions schema without the token tracking columns.
        await conn.execute(
            text(
                """
                CREATE TABLE chat_sessions (
                    id VARCHAR PRIMARY KEY,
                    site_id VARCHAR NOT NULL,
                    visitor_id VARCHAR(255),
                    page_url VARCHAR(2048),
                    messages JSON,
                    started_at DATETIME,
                    ended_at DATETIME
                )
                """
            )
        )

        await _migrate_add_columns(conn)

        columns_result = await conn.execute(text("PRAGMA table_info(chat_sessions)"))
        column_names = {row[1] for row in columns_result.fetchall()}

    await engine.dispose()

    assert "tokens_input" in column_names
    assert "tokens_output" in column_names
    assert "cost_usd" in column_names


@pytest.mark.asyncio
async def test_migrate_creates_knowledge_composite_indexes(tmp_path: Path):
    """knowledge_chunks must gain composite indexes for (site_id,*) queries."""
    db_path = tmp_path / "legacy_knowledge.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    async with engine.begin() as conn:
        # Legacy knowledge_chunks schema (no composite indexes).
        await conn.execute(
            text(
                """
                CREATE TABLE knowledge_chunks (
                    id VARCHAR PRIMARY KEY,
                    site_id VARCHAR NOT NULL,
                    source_url VARCHAR(2048),
                    source_type VARCHAR(50),
                    title VARCHAR(500),
                    content TEXT NOT NULL,
                    chunk_index INTEGER,
                    content_hash VARCHAR(64),
                    embedding_id VARCHAR(255),
                    crawled_at DATETIME
                )
                """
            )
        )

        await _migrate_add_columns(conn)

        idx_result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='knowledge_chunks'")
        )
        index_names = {row[0] for row in idx_result.fetchall()}

    await engine.dispose()

    assert "ix_knowledge_chunks_site_url" in index_names
    assert "ix_knowledge_chunks_site_hash" in index_names
