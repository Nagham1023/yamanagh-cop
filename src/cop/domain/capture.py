"""Capture detection (rules 46, 47): the ways a sub-game ends in the cop's favour.

Pure predicates over positions/barriers — no I/O, no network — so every
branch is directly unit-testable without a running game.

Detecting a capture locally (this module, rules 46/47, done since PRD 1)
was always a different concern from *declaring* it to the peer (rule 21,
**[FATAL]**) and the peer being cryptographically obliged to answer
truthfully (rule 22, **[FATAL]**) — PRD 6's `integrity/capture_protocol.py`
(`claim_capture`/`respond_to_capture_claim`) is that declaration channel;
this module still only ever produces the local, truthful fact it packages.
"""

from __future__ import annotations

from .barriers import BarrierSet
from .board import Board, Position
from .movement import DELTAS


def is_coordinate_capture(cop_pos: Position, thief_pos: Position) -> bool:
    """The pursuit-evasion base case: cop and thief occupy the same cell."""
    return cop_pos == thief_pos


def is_barrier_capture(barrier_target: Position, thief_pos: Position) -> bool:
    """Rule 46: a barrier dropped on the thief's current cell is an instant capture."""
    return barrier_target == thief_pos


def thief_has_no_legal_move(thief_pos: Position, board: Board, barriers: BarrierSet) -> bool:
    """Rule 47: true only if every orthogonal neighbour is off-board or barricaded.

    STAY is deliberately excluded from this check. The book's own gloss on
    rule 47 defines "imprisoned" as every *adjacent* cell being blocked by
    barriers and/or the board edge — a thief that can only ever stay in
    place is exactly that state, not a legal escape route.
    """
    for direction, delta in DELTAS.items():
        if direction == "STAY":
            continue
        neighbour = thief_pos + delta
        if board.in_bounds(neighbour) and not barriers.blocks(neighbour):
            return False
    return True
