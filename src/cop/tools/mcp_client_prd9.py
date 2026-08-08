"""Client call for PRD 9's one new tool — same thin, direct call/return
shape `mcp_client_prd6.py` already established; deadline/technical-loss
wrapping lives one layer up (`orchestrator_step0.py`).
"""

from __future__ import annotations

from typing import Any

from fastmcp import Client


async def send_step0(url: str, declaration: dict, signature: str, repos: dict) -> dict[str, Any]:
    async with Client(url) as client:
        result = await client.call_tool(
            "receive_step0",
            {"declaration": declaration, "signature": signature, "repos": repos},
        )
        return result.data
