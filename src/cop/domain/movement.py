"""Legal-move enforcement (rules 13, 14): orthogonal single steps or stay, nothing else.

A diagonal, a multi-cell jump, or an unrecognised token is rejected here
before it ever reaches capture or scoring logic — illegal-input rejection is
this layer's own test-coverage obligation (CLAUDE.md house rules), not just
a nice-to-have.
"""

from __future__ import annotations

from .board import Board, Position

# The book's movement set (Table 15 #1) is FIXED status — four orthogonal
# directions plus staying in place. This is never read from config; it is
# part of the rules of the game itself, not a negotiable parameter.
DELTAS: dict[str, Position] = {
    "N": Position(0, -1),
    "S": Position(0, 1),
    "E": Position(1, 0),
    "W": Position(-1, 0),
    "STAY": Position(0, 0),
}


def is_legal_direction(direction: str) -> bool:
    """True only for one of the five fixed tokens above — rejects diagonals by construction."""
    return direction in DELTAS


def apply_move(pos: Position, direction: str, board: Board) -> Position | None:
    """Return the destination cell, or None if the move is illegal or off-board."""
    if not is_legal_direction(direction):
        return None
    destination = pos + DELTAS[direction]
    if not board.in_bounds(destination):
        return None
    return destination
