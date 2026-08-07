"""Client calls for PRD 6's six new tools — split out of `mcp_client.py`,
same 150-line-cap reasoning as `mcp_server_prd6.py`'s split from
`mcp_server.py`. Each function is a thin, direct call/return — no retry,
no interpretation; `orchestrator_peer.py`'s deadline-guard/technical-loss
wrapping (`await_with_deadline`) lives one layer up, same pattern
`request_scent_map`/`send_hint` already used.
"""

from __future__ import annotations

from typing import Any

from fastmcp import Client


async def send_commit(url: str, h_commit: str) -> dict[str, Any]:
    async with Client(url) as client:
        result = await client.call_tool("receive_commit", {"h_commit": h_commit})
        return result.data


async def send_reveal(url: str, move: dict, hint_text: str) -> dict[str, Any]:
    async with Client(url) as client:
        result = await client.call_tool("receive_reveal", {"move": move, "hint_text": hint_text})
        return result.data


async def send_final_reveal(url: str, nonces: dict) -> dict[str, Any]:
    async with Client(url) as client:
        result = await client.call_tool("receive_final_reveal", {"nonces": nonces})
        return result.data


async def send_barrier_declaration(url: str, col: int, row: int) -> dict[str, Any]:
    async with Client(url) as client:
        result = await client.call_tool("receive_barrier_declaration", {"col": col, "row": row})
        return result.data


async def send_capture_claim(
    url: str, thief_col: int, thief_row: int, cop_col: int, cop_row: int, claimed_at_step: int
) -> dict[str, Any]:
    async with Client(url) as client:
        result = await client.call_tool(
            "receive_capture_claim",
            {
                "thief_col": thief_col,
                "thief_row": thief_row,
                "cop_col": cop_col,
                "cop_row": cop_row,
                "claimed_at_step": claimed_at_step,
            },
        )
        return result.data


async def send_capture_response(
    url: str, confirmed: bool, true_thief_col: int, true_thief_row: int
) -> dict[str, Any]:
    async with Client(url) as client:
        result = await client.call_tool(
            "receive_capture_response",
            {
                "confirmed": confirmed,
                "true_thief_col": true_thief_col,
                "true_thief_row": true_thief_row,
            },
        )
        return result.data
