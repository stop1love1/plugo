"""Tests for the tool executor."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools import ToolExecutor


@pytest.mark.asyncio
async def test_execute_tool_unsupported_method():
    """ToolExecutor should return error for unsupported HTTP methods."""
    executor = ToolExecutor()
    result = await executor.execute_tool(
        tool_meta={"method": "PATCH", "url": "https://example.com/api", "headers": {}},
        arguments={},
    )
    assert result["error"] == "Unsupported method: PATCH"


@pytest.mark.asyncio
async def test_execute_tool_timeout():
    """ToolExecutor should handle timeouts gracefully."""
    executor = ToolExecutor()
    result = await executor.execute_tool(
        tool_meta={
            "method": "GET",
            "url": "https://httpbin.org/delay/10",
            "headers": {},
        },
        arguments={},
        timeout=0.001,
    )
    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_execute_tool_invalid_url():
    """ToolExecutor should handle connection errors gracefully."""
    executor = ToolExecutor()
    result = await executor.execute_tool(
        tool_meta={
            "method": "GET",
            "url": "http://localhost:1/nonexistent",
            "headers": {},
        },
        arguments={},
        timeout=2.0,
    )
    assert result["success"] is False
    assert "error" in result
