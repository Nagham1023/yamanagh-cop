"""FastMCP server tool surface: `receive_hint` decodes a valid hint payload
and flags it if over-limit; `share_scent_map` returns this peer's own
scent field as structured numeric data (PRD 4 "Revision 3",
`todoFullFix.md` §C3/§C8).

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

import cop.tools.mcp_server as mcp_server_module
from cop.domain.board import Position
from cop.tools.mcp_server import _caller_ip, build_server


def _call(mcp, tool: str, arguments: dict):
    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(tool, arguments)
            return result.data

    return asyncio.run(run())


def test_receive_hint_decodes_a_valid_payload(config):
    mcp = build_server(config)
    data = _call(mcp, "receive_hint", {"text": "quiet by the river"})
    assert data == {"accepted": True, "word_count": 4}


def test_receive_hint_flags_a_hint_over_the_word_limit(config):
    mcp = build_server(config)
    over_limit_text = " ".join(["word"] * (config.hint_word_limit + 1))
    data = _call(mcp, "receive_hint", {"text": over_limit_text})
    assert data["accepted"] is False
    assert data["word_count"] == config.hint_word_limit + 1


def test_receive_hint_rejects_a_non_string_payload(config):
    mcp = build_server(config)
    with pytest.raises(ToolError):
        _call(mcp, "receive_hint", {"text": 12345})


def test_receive_hint_rejects_a_missing_argument(config):
    mcp = build_server(config)
    with pytest.raises(ToolError):
        _call(mcp, "receive_hint", {})


def test_on_receive_hook_fires_on_every_successful_receive_hint_call(config):
    calls = []
    mcp = build_server(config, on_receive=lambda ip: calls.append(ip))

    _call(mcp, "receive_hint", {"text": "north of the market"})
    _call(mcp, "receive_hint", {"text": "south of the bridge"})

    assert len(calls) == 2


def test_on_receive_hook_gets_none_over_the_in_process_test_transport(config):
    # No real HTTP layer at all in this transport — IP capture must
    # degrade to None, not raise.
    calls = []
    mcp = build_server(config, on_receive=lambda ip: calls.append(ip))

    _call(mcp, "receive_hint", {"text": "north of the market"})

    assert calls == [None]


def test_on_receive_hook_is_optional(config):
    # build_server's default (no on_receive) must not raise — proves the
    # hook is genuinely optional, not just untested in the happy path.
    mcp = build_server(config)
    data = _call(mcp, "receive_hint", {"text": "near the old market"})
    assert data == {"accepted": True, "word_count": 4}


def test_on_hint_hook_receives_the_text(config):
    received = []
    mcp = build_server(config, on_hint=lambda text: received.append(text))

    _call(mcp, "receive_hint", {"text": "north of the market"})

    assert received == ["north of the market"]


def test_caller_ip_prefers_the_x_forwarded_for_header_over_request_client_host(monkeypatch):
    # Isolated from any real HTTP transport, deliberately: uvicorn's own
    # ProxyHeadersMiddleware (trusted_hosts=127.0.0.1 by default) already
    # rewrites request.client.host to match X-Forwarded-For for any
    # locally-originating connection — every connection in this test suite,
    # and every real ngrok connection too (the tunnel's local forwarding
    # agent connects via loopback). A real-HTTP test alone can't distinguish
    # this function's own preference order from that middleware's, since
    # both produce the same answer — found while sanity-checking this exact
    # claim (see the reverted sabotage note in PRD-5-cloud-exposure.md).
    class _FakeClient:
        host = "127.0.0.1"

    class _FakeRequest:
        client = _FakeClient()

    monkeypatch.setattr(mcp_server_module, "get_http_headers", lambda: {"x-forwarded-for": "203.0.113.7"})
    monkeypatch.setattr(mcp_server_module, "get_http_request", lambda: _FakeRequest())

    assert _caller_ip() == "203.0.113.7"


def test_the_numeric_position_tool_is_gone(config):
    mcp = build_server(config)

    async def _tool_names() -> set[str]:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            return {tool.name for tool in tools}

    tool_names = asyncio.run(_tool_names())
    assert "receive_position" not in tool_names
    assert "receive_hint" in tool_names
    assert "share_scent_map" in tool_names


def test_share_scent_map_returns_the_wire_serialized_field(config):
    field_data = {Position(1, 1): 0.9, Position(2, 2): 0.42}
    mcp = build_server(config, get_scent_field=lambda: field_data)

    data = _call(mcp, "share_scent_map", {})

    assert set(data.keys()) == {"cells"}
    assert sorted(tuple(entry) for entry in data["cells"]) == [(1, 1, 0.9), (2, 2, 0.42)]


def test_share_scent_map_defaults_to_empty_when_no_hook_is_configured(config):
    mcp = build_server(config)

    data = _call(mcp, "share_scent_map", {})

    assert data == {"cells": []}


def test_share_scent_map_also_fires_on_receive(config):
    calls = []
    mcp = build_server(config, on_receive=lambda ip: calls.append(ip), get_scent_field=lambda: {})

    _call(mcp, "share_scent_map", {})

    assert len(calls) == 1
