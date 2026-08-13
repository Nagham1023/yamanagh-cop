"""Q-table state encoding (PRD 11; belief-entropy added PRD 14 sub-layer A,
switched from peak-probability to Shannon entropy in the post-gate
follow-up): a compact, board-size-agnostic key.

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

`belief_entropy` (PRD 14 sub-layer A, renamed from `belief_confidence` in
the post-gate follow-up) closes a real train/inference gap: `training/env.py
::SelfPlayEnv` used to feed this encoder the *true* relative position every
time (perfect information), but a real match's `RLCopBrain` receives the
belief map's *estimate* instead — a mismatch nobody had tested. Entropy
(`belief_entropy_bucket.py`) replaced peak-probability bucketing because it
captures how "modal" a distribution is far better: two distributions can
share the same peak probability while one is a clean single mode and the
other split across several, and only entropy tells them apart. Defaulted to
`0.0` — a point-mass distribution's entropy is *exactly* zero, so every
ground-truth caller (`run_local_subgame`, perfect-information by design) is
represented exactly, not approximated by an arbitrary stand-in.

`barriers`/`target_pos` (PRD 14 sub-layer B) grow two more derived features —
barrier-quota spent, target enclosure — both computed from parameters this
function already receives, no new parameter needed for either.

`second_mode_pos` (PRD 14 round-2 post-gate): an optional second belief
mode's own clamped relative vector (`dx2`, `dy2`), closing a real gap
`training/reward.py`'s own docstring already named — two belief
distributions can share the same argmax cell (identical `dx`, `dy`,
identical encoded state otherwise) while one is a clean single mode and the
other genuinely bimodal, and the tabular encoding used to have no way to
tell them apart. `None` (the common, genuinely-unimodal case, and every
ground-truth caller) encodes as `dx2 = dy2 = 0` — a safe sentinel
specifically because a real second mode can never coincide with the cop's
own position in any meaningful case, unlike indices 0/1 where `(0, 0)` is a
genuine reachable "target is here" state.
"""

from __future__ import annotations

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..domain.movement import apply_move
from .belief_entropy_bucket import bucket_entropy
from .rl_state_buckets import bucket_barrier_count, bucket_enclosure, clamp, count_open_neighbours

_CLAMP_RADIUS = 4

# One bit per orthogonal direction — set when moving that way right now is
# illegal, whether from the board edge or a real barrier. Before PRD 14 sub-
# layer B, barrier-adjacent states were never visited during training (self-
# play never placed one), so any state with a barrier-caused bit set was
# guaranteed to miss the table and fall back to the inherited CopBrain
# heuristic in RLCopBrain. Sub-layer B changes that (see rl_cop_brain.py).
_BIT_ORDER = ("N", "E", "S", "W")

State = tuple[int, int, int, int, int, int, int, int]


def encode_state(
    own_pos: Position,
    target_pos: Position,
    board: Board,
    barriers: BarrierSet,
    *,
    belief_entropy: float = 0.0,
    second_mode_pos: Position | None = None,
) -> State:
    """Same parameter order as `BrainBase._pick_move` — the encoding is
    computed from exactly what a brain already receives, no extra plumbing
    needed at either training or inference time. `belief_entropy` and
    `second_mode_pos` are keyword-only and defaulted so every pre-existing
    positional call site (ground-truth training, `run_local_subgame`) keeps
    working unchanged — see the module docstring."""
    dx = clamp(target_pos.col - own_pos.col, _CLAMP_RADIUS)
    dy = clamp(target_pos.row - own_pos.row, _CLAMP_RADIUS)
    bitmask = 0
    for index, direction in enumerate(_BIT_ORDER):
        destination = apply_move(own_pos, direction, board)
        blocked = destination is None or barriers.blocks(destination)
        if blocked:
            bitmask |= 1 << index
    barrier_count_bucket = bucket_barrier_count(len(barriers.placed), barriers.quota)
    enclosure_bucket = bucket_enclosure(count_open_neighbours(target_pos, board, barriers))
    if second_mode_pos is None:
        dx2 = dy2 = 0
    else:
        dx2 = clamp(second_mode_pos.col - own_pos.col, _CLAMP_RADIUS)
        dy2 = clamp(second_mode_pos.row - own_pos.row, _CLAMP_RADIUS)
    return (
        dx, dy, bitmask, bucket_entropy(belief_entropy), barrier_count_bucket, enclosure_bucket,
        dx2, dy2,
    )
