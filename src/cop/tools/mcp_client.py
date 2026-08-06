"""Calls into a peer's FastMCP server.

Async, matching FastMCP's own `Client` design — the deadline tracker (PRD 2
§3) wraps calls like this one with `asyncio.wait_for`, which only composes
cleanly with an async call in the first place.
"""

from __future__ import annotations

from typing import Any

from fastmcp import Client


async def send_hint(url: str, text: str) -> dict[str, Any]:
    """Call the peer's `receive_hint` tool over HTTP; return its ack dict."""
    async with Client(url) as client:
        result = await client.call_tool("receive_hint", {"text": text})
        return result.data
