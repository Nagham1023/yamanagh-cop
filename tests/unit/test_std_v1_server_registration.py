"""std_v1/server_registration.py tests — in-process `Client`, same
pattern `test_mcp_server_prd9.py` already uses for the native protocol's
own tool surface."""

from __future__ import annotations

import asyncio

from fastmcp import Client, FastMCP

from cop.std_v1.exchange import StdExchange
from cop.std_v1.server_registration import register_std_v1_tools


def _call(mcp, tool: str, arguments: dict):
    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(tool, arguments)
            return result.data

    return asyncio.run(run())


def _server():
    exchange = StdExchange(poll_interval=0.01)
    mcp = FastMCP(name="cop_peer_std_v1_test")
    register_std_v1_tools(mcp, exchange)
    return mcp, exchange


def test_all_four_tools_are_registered():
    mcp, _exchange = _server()

    async def _tool_names():
        async with Client(mcp) as client:
            tools = await client.list_tools()
            return {tool.name for tool in tools}

    names = asyncio.run(_tool_names())
    assert {"negotiate", "receive_turn", "submit_audit", "receive_control"} <= names


def test_negotiate_lands_on_the_exchange_and_acks():
    mcp, exchange = _server()
    data = _call(mcp, "negotiate", {"message": {"sub_game_number": 1, "group_id": "g"}})
    assert data == {"ok": True}
    assert exchange.wait_for_offer(1, timeout=1.0)["group_id"] == "g"


def test_receive_turn_lands_on_the_exchange():
    mcp, exchange = _server()
    _call(mcp, "receive_turn", {"message": {"step": 3, "sender": "thief"}})
    assert exchange.wait_for_turn(3, timeout=1.0)["sender"] == "thief"


def test_submit_audit_uses_the_payload_kwarg():
    mcp, exchange = _server()
    _call(
        mcp, "submit_audit",
        {"payload": {"sub_game_number": 2, "result_claim": "capture", "sender": "police", "records": []}},
    )
    assert exchange.wait_for_audit(2, timeout=1.0)["result_claim"] == "capture"


def test_receive_control_lands_on_the_exchange():
    mcp, exchange = _server()
    _call(mcp, "receive_control", {"message": {"type": "ping"}})
    assert exchange.latest_control() == {"type": "ping"}
