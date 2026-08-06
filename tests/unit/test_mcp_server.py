"""FastMCP server tool surface: decodes valid payloads, rejects malformed ones.

Uses FastMCP's in-process `Client(mcp)` transport — a real client/server
round-trip through the actual library, no mocking, just without opening a
real TCP port (that's what the two-process integration test is for).
"""

from __future__ import annotations

import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from cop.tools.mcp_server import build_server


def _call(mcp, arguments: dict):
    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool("receive_position", arguments)
            return result.data

    return asyncio.run(run())


def test_receive_position_decodes_a_valid_in_bounds_payload(config):
    mcp = build_server(config)
    data = _call(mcp, {"col": 3, "row": 4})
    assert data == {"accepted": True, "col": 3, "row": 4}


def test_receive_position_flags_an_off_board_cell(config):
    mcp = build_server(config)
    data = _call(mcp, {"col": config.board_size, "row": 0})
    assert data == {"accepted": False, "col": config.board_size, "row": 0}


def test_receive_position_rejects_a_non_integer_column(config):
    mcp = build_server(config)
    with pytest.raises(ToolError):
        _call(mcp, {"col": "not-an-int", "row": 0})


def test_receive_position_rejects_a_missing_argument(config):
    mcp = build_server(config)
    with pytest.raises(ToolError):
        _call(mcp, {"col": 3})


def test_on_receive_hook_fires_on_every_successful_call(config):
    calls = []
    mcp = build_server(config, on_receive=lambda: calls.append(1))

    _call(mcp, {"col": 1, "row": 1})
    _call(mcp, {"col": 2, "row": 2})

    assert len(calls) == 2


def test_on_receive_hook_is_optional(config):
    # build_server's default (no on_receive) must not raise — proves the
    # hook is genuinely optional, not just untested in the happy path.
    mcp = build_server(config)
    data = _call(mcp, {"col": 1, "row": 1})
    assert data == {"accepted": True, "col": 1, "row": 1}
