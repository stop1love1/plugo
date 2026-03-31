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
