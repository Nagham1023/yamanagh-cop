"""Client call for PRD 9's one new tool — same thin, direct call/return
shape `mcp_client_prd6.py` already established, through a persistent,
match-scoped `PeerConnection` (`peer_connection.py`); deadline/technical
-loss wrapping lives one layer up (`orchestrator_step0.py`).
"""

from __future__ import annotations

from typing import Any

from .peer_connection import PeerConnection


async def send_step0(
    connection: PeerConnection, declaration: dict, signature: str, repos: dict
) -> dict[str, Any]:
    result = await connection.call_tool(
        "receive_step0",
        {"declaration": declaration, "signature": signature, "repos": repos},
    )
    return result.data
