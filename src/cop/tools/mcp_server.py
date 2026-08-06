"""FastMCP server exposing this peer's tool surface.

One tool: `receive_position(col, row)` — a peer announcing a position. Rule
25 means this never decides anything: it validates the two ints are on the
board (board geometry, reusing PRD 1's `Board` — not strategy, so this is
legitimate to reuse here) and acknowledges. Rule 27's PRD 2 carve-out is
what makes bare ints legal at all; PRD 4 replaces this tool with a
free-language hint instead of coordinates.

`on_receive` is an optional hook, called on every successful call — the
Orchestrator wires it to the watchdog's `heartbeat()` so rule 7's watchdog
has something real to measure staleness against (activity from the peer),
not just wall-clock time since process start.
"""

from __future__ import annotations

from collections.abc import Callable

from fastmcp import FastMCP

from ..domain.board import Board, Position
from ..shared.config import GameConfig


def build_server(
    config: GameConfig,
    name: str = "cop_peer",
    on_receive: Callable[[], None] | None = None,
) -> FastMCP:
    """Construct a fresh FastMCP server bound to this config's board size."""
    board = Board(size=config.board_size)
    mcp = FastMCP(name)

    @mcp.tool
    def receive_position(col: int, row: int) -> dict:
        """Accept a peer's announced position; ack, or flag it as off-board."""
        if on_receive is not None:
            on_receive()
        accepted = board.in_bounds(Position(col, row))
        return {"accepted": accepted, "col": col, "row": row}

    return mcp
