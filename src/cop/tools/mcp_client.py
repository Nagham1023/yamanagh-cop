"""Calls into a peer's FastMCP server.

Async, matching FastMCP's own `Client` design — the deadline tracker (PRD 2
§3) wraps calls like this one with `asyncio.wait_for`, which only composes
cleanly with an async call in the first place.

`request_scent_map` (PRD 4 "Revision 3", `todoFullFix.md` §C3) is the
client half of `mcp_server.py`'s `share_scent_map` tool — deserializes the
peer's own scent field back into `dict[Position, float]`, ready for
`memory.belief.BeliefMap.update_from_scent_map`.
"""

from __future__ import annotations

from typing import Any

from fastmcp import Client

from ..domain.board import Position
from .scent_wire import deserialize_scent_field


async def send_hint(url: str, text: str) -> dict[str, Any]:
    """Call the peer's `receive_hint` tool over HTTP; return its ack dict."""
    async with Client(url) as client:
        result = await client.call_tool("receive_hint", {"text": text})
        return result.data


async def request_scent_map(url: str) -> dict[Position, float]:
    """Call the peer's `share_scent_map` tool over HTTP; return its own
    scent field, deserialized."""
    async with Client(url) as client:
        result = await client.call_tool("share_scent_map", {})
        return deserialize_scent_field(result.data)
