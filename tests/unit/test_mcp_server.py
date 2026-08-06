"""FastMCP server tool surface: decodes valid hint+scent-report payloads,
flags either field if it's over-limit (Revision 1's two-field shape).

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
from cop.tools.mcp_server import _caller_ip, build_server


def _call(mcp, arguments: dict):
    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool("receive_hint", arguments)
            return result.data

    return asyncio.run(run())


def test_receive_hint_decodes_a_valid_payload(config):
    mcp = build_server(config)
    data = _call(mcp, {"text": "quiet by the river", "scent_report": "Scent strongest to the north west."})
    assert data == {"accepted": True, "word_count": 4, "scent_word_count": 6}


def test_receive_hint_flags_a_hint_over_the_word_limit(config):
    mcp = build_server(config)
    over_limit_text = " ".join(["word"] * (config.hint_word_limit + 1))
    data = _call(mcp, {"text": over_limit_text, "scent_report": "Scent strongest to the north west."})
    assert data["accepted"] is False
    assert data["word_count"] == config.hint_word_limit + 1


def test_receive_hint_flags_a_scent_report_over_the_word_limit(config):
    mcp = build_server(config)
    over_limit_scent = " ".join(["word"] * (config.hint_word_limit + 1))
    data = _call(mcp, {"text": "quiet by the river", "scent_report": over_limit_scent})
    assert data["accepted"] is False
    assert data["scent_word_count"] == config.hint_word_limit + 1


def test_receive_hint_rejects_a_non_string_payload(config):
    mcp = build_server(config)
    with pytest.raises(ToolError):
        _call(mcp, {"text": 12345, "scent_report": "Scent strongest to the north west."})


def test_receive_hint_rejects_a_missing_argument(config):
    mcp = build_server(config)
    with pytest.raises(ToolError):
        _call(mcp, {"text": "quiet by the river"})


def test_on_receive_hook_fires_on_every_successful_call(config):
    calls = []
    mcp = build_server(config, on_receive=lambda ip: calls.append(ip))

    _call(mcp, {"text": "north of the market", "scent_report": "Scent strongest to the north west."})
    _call(mcp, {"text": "south of the bridge", "scent_report": "Scent strongest to the south east."})

    assert len(calls) == 2


def test_on_receive_hook_gets_none_over_the_in_process_test_transport(config):
    # No real HTTP layer at all in this transport — IP capture must
    # degrade to None, not raise.
    calls = []
    mcp = build_server(config, on_receive=lambda ip: calls.append(ip))

    _call(mcp, {"text": "north of the market", "scent_report": "Scent strongest to the north west."})

    assert calls == [None]


def test_on_receive_hook_is_optional(config):
    # build_server's default (no on_receive) must not raise — proves the
    # hook is genuinely optional, not just untested in the happy path.
    mcp = build_server(config)
    data = _call(mcp, {"text": "near the old market", "scent_report": "Scent strongest to the north west."})
    assert data == {"accepted": True, "word_count": 4, "scent_word_count": 6}


def test_on_hint_hook_receives_both_fields(config):
    received = []
    mcp = build_server(config, on_hint=lambda text, scent_report: received.append((text, scent_report)))

    _call(mcp, {"text": "north of the market", "scent_report": "Scent strongest to the south east."})

    assert received == [("north of the market", "Scent strongest to the south east.")]


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
