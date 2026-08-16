"""Calls into a peer's FastMCP server.

Async, matching FastMCP's own `Client` design — the deadline tracker (PRD 2
§3) wraps calls like this one with `asyncio.wait_for`, which only composes
cleanly with an async call in the first place.

`request_scent_map` (PRD 4 "Revision 3", `todoFullFix.md` §C3) is the
client half of `mcp_server.py`'s `share_scent_map` tool — deserializes the
peer's own scent field back into `dict[Position, float]`, ready for
`memory.belief.BeliefMap.update_from_scent_map`. PRD 6's six new client
calls (`send_commit`, `send_reveal`, ...) live in `mcp_client_prd6.py` —
`send_reveal` supersedes this module's old `send_hint`
(`mcp_server_prd6.py`'s own docstring has the full reasoning).

Takes a `PeerConnection` (`peer_connection.py`), not a bare URL — one
persistent connection reused for the whole match, not a fresh one per
call (found necessary live: dozens of fresh connections through one
free-tier ngrok tunnel by round 5-6 was what actually degraded real
matches, not any single logic bug)."""

from __future__ import annotations

from ..domain.board import Position
from .peer_connection import PeerConnection
from .scent_wire import deserialize_scent_field


async def request_scent_map(connection: PeerConnection) -> dict[Position, float]:
    """Call the peer's `share_scent_map` tool; return its own scent
    field, deserialized."""
    result = await connection.call_tool("share_scent_map", {})
    return deserialize_scent_field(result.data)
