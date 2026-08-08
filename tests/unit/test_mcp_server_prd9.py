"""PRD 9's one new server tool, `receive_step0` (`mcp_server_prd9.py`) —
in-process `Client`, same pattern `test_mcp_server_prd6.py` already uses.
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


def test_receive_step0_is_registered(config):
    mcp = build_server(config)

    async def _tool_names() -> set[str]:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            return {tool.name for tool in tools}

    assert "receive_step0" in asyncio.run(_tool_names())


def test_receive_step0_acknowledges_when_no_callback_is_wired(config):
    mcp = build_server(config)
    data = _call(
        mcp, "receive_step0", {"declaration": {"a": 1}, "signature": "s", "repos": {}}
    )
    assert data == {"acknowledged": True}


def test_receive_step0_fires_on_step0_and_returns_its_result(config):
    received = []

    def _on_step0(declaration, signature, repos):
        received.append((declaration, signature, repos))
        return {"declaration": {"echo": True}, "signature": "reply-sig", "repos": {"cop": "x"}}

    mcp = build_server(config, on_step0=_on_step0)
    data = _call(
        mcp,
        "receive_step0",
        {"declaration": {"group_name": "peer"}, "signature": "peer-sig", "repos": {"cop": "y"}},
    )

    assert received == [({"group_name": "peer"}, "peer-sig", {"cop": "y"})]
    assert data == {"declaration": {"echo": True}, "signature": "reply-sig", "repos": {"cop": "x"}}
