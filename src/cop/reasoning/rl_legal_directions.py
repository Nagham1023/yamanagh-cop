"""`_legal_directions` split out of `rl_cop_brain.py` once that file grew
past the 150-line house cap adding the `second_mode_provider` seam — a
single, self-contained helper with no other coupling to the rest of that
file.
"""

from __future__ import annotations

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..domain.movement import DELTAS, apply_move


def legal_directions(own_pos: Position, board: Board, barriers: BarrierSet) -> set[str]:
    """Every direction whose destination is on-board and unblocked, plus
    `STAY` (always legal) — the same check `CopBrain._pick_move` already
    performs per-candidate, computed once here as a set for a ranked-list
    intersection."""
    legal = {"STAY"}
    for direction in DELTAS:
        if direction == "STAY":
            continue
        destination = apply_move(own_pos, direction, board)
        if destination is not None and not barriers.blocks(destination):
            legal.add(direction)
    return legal
