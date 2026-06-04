"""Tests for the tool executor."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools import ToolExecutor, validate_tool_arguments


def test_validate_tool_arguments_accepts_correct_types():
    schema = {
        "type": "object",
        "properties": {"city": {"type": "string"}, "days": {"type": "integer"}},
        "required": ["city"],
    }
    ok, err = validate_tool_arguments(schema, {"city": "Hanoi", "days": 3})
    assert ok is True
    assert err is None


def test_validate_tool_arguments_rejects_missing_required():
    schema = {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}
    ok, err = validate_tool_arguments(schema, {})
    assert ok is False
    assert "city" in err and "required" in err.lower()


def test_validate_tool_arguments_rejects_wrong_type():
    schema = {"type": "object", "properties": {"days": {"type": "integer"}}, "required": []}
    ok, err = validate_tool_arguments(schema, {"days": "three"})
    assert ok is False
    assert "days" in err


def test_validate_tool_arguments_rejects_bool_for_number():
    """bool is a subclass of int in Python — must not pass as a number/integer."""
    schema = {"type": "object", "properties": {"days": {"type": "integer"}}, "required": []}
    ok, _ = validate_tool_arguments(schema, {"days": True})
    assert ok is False


def test_validate_tool_arguments_tolerates_empty_schema_and_extra_params():
    assert validate_tool_arguments({}, {"anything": 1})[0] is True
    assert validate_tool_arguments(None, {"anything": 1})[0] is True
    # Unknown params (not in properties) are tolerated.
    schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": []}
    assert validate_tool_arguments(schema, {"a": "x", "extra": 99})[0] is True


@pytest.mark.asyncio
async def test_execute_tool_rejects_invalid_arguments_before_http():
    """Invalid LLM-provided arguments must be rejected before any HTTP/SSRF work,
    so a malformed call never reaches the network."""
    executor = ToolExecutor()
    result = await executor.execute_tool(
        tool_meta={
            "method": "GET",
            "url": "https://example.com/api",
            "headers": {},
            "parameters": {
                "type": "object",
                "properties": {"count": {"type": "integer"}},
                "required": ["count"],
            },
        },
        arguments={"count": "not-a-number"},
    )
    assert result["success"] is False
    assert result["error"].startswith("Invalid arguments")


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
