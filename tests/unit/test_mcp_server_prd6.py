"""PRD 6's remaining five server tools (`mcp_server_prd6.py`):
`receive_commit`, `receive_final_reveal`, `receive_barrier_declaration`,
`receive_capture_claim`, `receive_capture_response`. `receive_reveal` has
its own tests in `test_mcp_server.py` alongside the rest of the core
surface it supersedes.
"""

from __future__ import annotations

import asyncio

from fastmcp import Client

from cop.tools.mcp_server import build_server


def _call(mcp, tool: str, arguments: dict):
    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(tool, arguments)
            return result.data

    return asyncio.run(run())


def test_all_prd6_tools_are_registered(config):
    mcp = build_server(config)

    async def _tool_names() -> set[str]:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            return {tool.name for tool in tools}

    tool_names = asyncio.run(_tool_names())
    assert {
        "receive_commit",
        "receive_reveal",
        "receive_final_reveal",
        "receive_barrier_declaration",
        "receive_capture_claim",
        "receive_capture_response",
    } <= tool_names


def test_receive_commit_acknowledges_and_fires_on_commit(config):
    received = []
    mcp = build_server(config, on_commit=lambda h: received.append(h))

    data = _call(mcp, "receive_commit", {"h_commit": "a" * 64})

    assert data == {"acknowledged": True}
    assert received == ["a" * 64]


def test_receive_final_reveal_acknowledges_and_fires_on_final_reveal(config):
    received = []
    mcp = build_server(config, on_final_reveal=lambda nonces: received.append(nonces))

    data = _call(mcp, "receive_final_reveal", {"nonces": {"0": "b" * 32}})

    assert data == {"acknowledged": True}
    assert received == [{"0": "b" * 32}]


def test_receive_barrier_declaration_acknowledges_and_fires_on_barrier_declaration(config):
    received = []
    mcp = build_server(config, on_barrier_declaration=lambda col, row: received.append((col, row)))

    data = _call(mcp, "receive_barrier_declaration", {"col": 3, "row": 4})

    assert data == {"acknowledged": True}
    assert received == [(3, 4)]


def test_receive_capture_claim_acknowledges_and_fires_on_capture_claim(config):
    received = []
    mcp = build_server(
        config,
        on_capture_claim=lambda tc, tr, cc, cr, step: received.append((tc, tr, cc, cr, step)),
    )

    data = _call(
        mcp,
        "receive_capture_claim",
        {"thief_col": 3, "thief_row": 3, "cop_col": 3, "cop_row": 3, "claimed_at_step": 7},
    )

    assert data == {"acknowledged": True}
    assert received == [(3, 3, 3, 3, 7)]


def test_receive_capture_response_acknowledges_and_fires_on_capture_response(config):
    received = []
    mcp = build_server(
        config,
        on_capture_response=lambda confirmed, col, row: received.append((confirmed, col, row)),
    )

    data = _call(
        mcp, "receive_capture_response", {"confirmed": False, "true_thief_col": 5, "true_thief_row": 1}
    )

    assert data == {"acknowledged": True}
    assert received == [(False, 5, 1)]


def test_on_receive_fires_on_final_reveal_capture_claim_and_capture_response(config):
    calls = []
    mcp = build_server(config, on_receive=lambda ip: calls.append(ip))

    _call(mcp, "receive_final_reveal", {"nonces": {}})
    _call(
        mcp,
        "receive_capture_claim",
        {"thief_col": 0, "thief_row": 0, "cop_col": 0, "cop_row": 0, "claimed_at_step": 0},
    )
    _call(mcp, "receive_capture_response", {"confirmed": True, "true_thief_col": 0, "true_thief_row": 0})

    assert len(calls) == 3


def test_every_prd6_callback_is_optional(config):
    # None of the six new callbacks raise when omitted — every tool must
    # still work with build_server's own bare defaults.
    mcp = build_server(config)

    assert _call(mcp, "receive_commit", {"h_commit": "a" * 64}) == {"acknowledged": True}
    assert _call(mcp, "receive_final_reveal", {"nonces": {}}) == {"acknowledged": True}
    assert _call(mcp, "receive_barrier_declaration", {"col": 0, "row": 0}) == {"acknowledged": True}
    assert _call(
        mcp,
        "receive_capture_claim",
        {"thief_col": 0, "thief_row": 0, "cop_col": 0, "cop_row": 0, "claimed_at_step": 0},
    ) == {"acknowledged": True}
    assert _call(
        mcp, "receive_capture_response", {"confirmed": True, "true_thief_col": 0, "true_thief_row": 0}
    ) == {"acknowledged": True}
