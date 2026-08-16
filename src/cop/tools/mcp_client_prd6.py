"""Client calls for PRD 6's six new tools — split out of `mcp_client.py`,
same 150-line-cap reasoning as `mcp_server_prd6.py`'s split from
`mcp_server.py`. Each function is a thin, direct call/return through a
persistent, match-scoped `PeerConnection` (`peer_connection.py`) — no
retry *within* one call on a timeout or a transient failure anywhere in
this module (WIRE-CONTRACT.md's Status log has the reasoning: a peer may
have already applied a non-idempotent call, so retrying blind risks a
duplicate); `orchestrator_peer.py`'s deadline-guard/technical-loss
wrapping (`await_with_deadline`) lives one layer up, same pattern
`request_scent_map`/`send_hint` already used.

`send_commit`/`send_reveal` are the one deliberate exception, and only for
one specific, provably-safe case: a peer whose own `receive_commit`/
`receive_reveal` predates PRD 15's `sent_at`/`deadline_at` fields rejects
the call *before* its tool body ever runs (FastMCP validates arguments
first) — found live against the thief repo's own server, which still
sends the old (correct, PRD-15-era) shape but never asked for the new
fields to be added on their own receiving side. Unlike a timeout retry,
this one is safe: the rejected attempt is *guaranteed* never applied, so
falling back to the old, universally-compatible shape can't double-apply
anything — and `PeerConnection.call_tool` deliberately never treats a
`ToolError` (this rejection's own exception type) as a connection
failure, so the same session stays open for the fallback call below.
"""

from __future__ import annotations

from typing import Any

from fastmcp.exceptions import ToolError

from .peer_connection import PeerConnection

_TIMING_FIELDS = ("sent_at", "deadline_at")


def _rejected_for_new_timing_fields(exc: ToolError) -> bool:
    """`True` only for the exact rejection PRD 15 can cause on an older
    peer — a schema-validation failure naming one of the new optional
    fields as unexpected. Anything else (a real connection failure, a
    different validation error) re-raises unchanged; this is not a
    general-purpose retry."""
    message = str(exc)
    return "unexpected_keyword_argument" in message and any(field in message for field in _TIMING_FIELDS)


async def send_commit(
    connection: PeerConnection, h_commit: str, sent_at: float, deadline_at: float
) -> dict[str, Any]:
    try:
        result = await connection.call_tool(
            "receive_commit", {"h_commit": h_commit, "sent_at": sent_at, "deadline_at": deadline_at}
        )
    except ToolError as exc:
        if not _rejected_for_new_timing_fields(exc):
            raise
        result = await connection.call_tool("receive_commit", {"h_commit": h_commit})
    return result.data


async def send_reveal(
    connection: PeerConnection, move: dict, hint_text: str, sent_at: float, deadline_at: float
) -> dict[str, Any]:
    try:
        result = await connection.call_tool(
            "receive_reveal",
            {"move": move, "hint_text": hint_text, "sent_at": sent_at, "deadline_at": deadline_at},
        )
    except ToolError as exc:
        if not _rejected_for_new_timing_fields(exc):
            raise
        result = await connection.call_tool("receive_reveal", {"move": move, "hint_text": hint_text})
    return result.data


async def send_final_reveal(connection: PeerConnection, nonces: dict, intents: dict) -> dict[str, Any]:
    result = await connection.call_tool("receive_final_reveal", {"nonces": nonces, "intents": intents})
    return result.data


async def send_barrier_declaration(connection: PeerConnection, col: int, row: int) -> dict[str, Any]:
    result = await connection.call_tool("receive_barrier_declaration", {"col": col, "row": row})
    return result.data


async def send_capture_claim(
    connection: PeerConnection,
    thief_col: int,
    thief_row: int,
    cop_col: int,
    cop_row: int,
    claimed_at_step: int,
) -> dict[str, Any]:
    result = await connection.call_tool(
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
    connection: PeerConnection, confirmed: bool, true_thief_col: int, true_thief_row: int
) -> dict[str, Any]:
    result = await connection.call_tool(
        "receive_capture_response",
        {
            "confirmed": confirmed,
            "true_thief_col": true_thief_col,
            "true_thief_row": true_thief_row,
        },
    )
    return result.data
