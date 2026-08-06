"""FastMCP server tool surface: decodes valid hints, flags over-limit ones.

Uses FastMCP's in-process `Client(mcp)` transport — a real client/server
round-trip through the actual library, no mocking, just without opening a
real TCP port (that's what the two-process integration test is for).

PRD 2's `receive_position(col, row)` carve-out is gone. This file's own
`test_the_numeric_position_tool_is_gone` used to be a strict xfail guarding
that removal; now that the tool is actually gone, it's a plain passing
assertion (leaving the old xfail marker behind after this point would have
XPASS'd and hard-failed the suite, which is exactly why it's deleted in
this same commit, not just relaxed).
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
            result = await client.call_tool("receive_hint", arguments)
            return result.data

    return asyncio.run(run())


def test_receive_hint_decodes_a_valid_payload(config):
    mcp = build_server(config)
    data = _call(mcp, {"text": "quiet by the river"})
    assert data == {"accepted": True, "word_count": 4}


def test_receive_hint_flags_a_hint_over_the_word_limit(config):
    mcp = build_server(config)
    over_limit_text = " ".join(["word"] * (config.hint_word_limit + 1))
    data = _call(mcp, {"text": over_limit_text})
    assert data == {"accepted": False, "word_count": config.hint_word_limit + 1}


def test_receive_hint_rejects_a_non_string_payload(config):
    mcp = build_server(config)
    with pytest.raises(ToolError):
        _call(mcp, {"text": 12345})


def test_receive_hint_rejects_a_missing_argument(config):
    mcp = build_server(config)
    with pytest.raises(ToolError):
        _call(mcp, {})


def test_on_receive_hook_fires_on_every_successful_call(config):
    calls = []
    mcp = build_server(config, on_receive=lambda: calls.append(1))

    _call(mcp, {"text": "north of the market"})
    _call(mcp, {"text": "south of the bridge"})

    assert len(calls) == 2


def test_on_receive_hook_is_optional(config):
    # build_server's default (no on_receive) must not raise — proves the
    # hook is genuinely optional, not just untested in the happy path.
    mcp = build_server(config)
    data = _call(mcp, {"text": "near the old market"})
    assert data == {"accepted": True, "word_count": 4}


def test_the_numeric_position_tool_is_gone(config):
    mcp = build_server(config)

    async def _tool_names() -> set[str]:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            return {tool.name for tool in tools}

    tool_names = asyncio.run(_tool_names())
    assert "receive_position" not in tool_names
    assert "receive_hint" in tool_names
