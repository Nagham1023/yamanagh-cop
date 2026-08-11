"""Q-table state encoding (PRD 11): a compact, board-size-agnostic key.

Absolute-position encoding would blow up combinatorially as `board.size`
grows (Table 13's `grid_size` is a MINIMUM, negotiable upward) and would not
generalize between symmetric chases — a Q-value learned at (0,0)->(3,3)
teaches nothing about (4,4)->(0,0), even though it is the same relative
chase. Relative displacement, clamped to a fixed radius, fixes both: the
state space stays bounded regardless of board size, and a learned value
transfers across the board.

`_CLAMP_RADIUS` is a fixed algorithm-shape constant, not derived from
`board.size` — deliberately, so the table's size doesn't grow if the board
does; distances beyond the radius all fold into the same "far" bucket,
still correctly biased toward closing the gap. Same "not I6" category as
`cop_brain.py`'s `_TIE_BREAK_ORDER`: an implementation choice, not a
negotiated game-rule quantity.
"""

from __future__ import annotations

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..domain.movement import apply_move

_CLAMP_RADIUS = 4

# One bit per orthogonal direction — set when moving that way right now is
# illegal, whether from the board edge or a real barrier. Barrier-adjacent
# states are never visited during training (PRD 11 never places barriers in
# self-play, see training/env.py), so any state with a barrier-caused bit
# set is guaranteed to miss the table and fall back to the inherited
# CopBrain heuristic in RLCopBrain — the intended, documented degradation.
_BIT_ORDER = ("N", "E", "S", "W")

State = tuple[int, int, int]


def _clamp(value: int, radius: int) -> int:
    """Saturate `value` to `[-radius, radius]` — every displacement beyond
    the radius folds into the same boundary value (see module docstring)."""
    return max(-radius, min(radius, value))


def encode_state(own_pos: Position, target_pos: Position, board: Board, barriers: BarrierSet) -> State:
    """Same parameter order as `BrainBase._pick_move` — the encoding is
    computed from exactly what a brain already receives, no extra plumbing
    needed at either training or inference time."""
    dx = _clamp(target_pos.col - own_pos.col, _CLAMP_RADIUS)
    dy = _clamp(target_pos.row - own_pos.row, _CLAMP_RADIUS)
    bitmask = 0
    for index, direction in enumerate(_BIT_ORDER):
        destination = apply_move(own_pos, direction, board)
        blocked = destination is None or barriers.blocks(destination)
        if blocked:
            bitmask |= 1 << index
    return (dx, dy, bitmask)
