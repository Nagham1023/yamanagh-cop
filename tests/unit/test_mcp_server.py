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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RULE-27-REMOVE-AT-PRD-4: receive_position's bare-coordinate protocol "
        "is legal only until PRD 4 ships the natural-language hint tool. Once "
        "PRD 4 removes it, this assertion starts passing (XPASS) — strict=True "
        "turns that into a hard failure, forcing this marker's own deletion in "
        "the same commit instead of quietly surviving into a real match."
    ),
)
def test_the_numeric_position_tool_is_gone_once_prd4_lands(config):
    # RULE-27-REMOVE-AT-PRD-4
    mcp = build_server(config)

    async def _tool_names() -> set[str]:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            return {tool.name for tool in tools}

    assert "receive_position" not in asyncio.run(_tool_names())
