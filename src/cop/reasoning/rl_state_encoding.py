"""Q-table state encoding (PRD 11; belief-confidence added PRD 14 sub-layer
A): a compact, board-size-agnostic key.

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

`belief_confidence` (PRD 14 sub-layer A) closes a real train/inference gap:
`training/env.py::SelfPlayEnv` used to feed this encoder the *true* relative
position every time (perfect information), but a real match's `RLCopBrain`
receives the belief map's *estimate* instead (`target_pos` arrives via
`reasoning/state.py::ground_truth_target_position`'s belief-map seam) — a
mismatch nobody had tested. The keyword is defaulted to `1.0` (maximal
confidence) precisely because every ground-truth caller (`run_local_subgame`,
which stays perfect-information by design, PRD-4's own decision) *is*
maximally confident — no existing call site needs to change to keep working
exactly as before.

`barriers`/`target_pos` (PRD 14 sub-layer B) grow two more derived features —
barrier-quota spent, target enclosure — both computed from parameters this
function already receives, no new parameter needed for either.
"""

from __future__ import annotations

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..domain.movement import DELTAS, apply_move

_CLAMP_RADIUS = 4

# One bit per orthogonal direction — set when moving that way right now is
# illegal, whether from the board edge or a real barrier. Before PRD 14 sub-
# layer B, barrier-adjacent states were never visited during training (self-
# play never placed one), so any state with a barrier-caused bit set was
# guaranteed to miss the table and fall back to the inherited CopBrain
# heuristic in RLCopBrain. Sub-layer B changes that (see rl_cop_brain.py).
_BIT_ORDER = ("N", "E", "S", "W")

# Peak belief probability -> a coarse confidence bucket. Fixed thresholds,
# same "algorithm constant, not I6" category as _CLAMP_RADIUS/_BIT_ORDER —
# the book gives no specific number for a "reliability"/"confidence" cutoff,
# this is this repo's own tuning choice. Four buckets: near-uniform ("no
# idea"), two intermediate levels, and "confident" (includes the 1.0
# ground-truth case every pre-A caller still produces).
_CONFIDENCE_THRESHOLDS = (0.15, 0.35, 0.6)

State = tuple[int, int, int, int, int, int]


def _bucket_barrier_count(count: int, quota: int) -> int:
    """Quota-*relative*, not a fixed literal cutoff (e.g. 0/1-4/5-9/10-14):
    `max_barriers` is a Table 15 MINIMUM, negotiable upward — a hardcoded
    boundary would silently misbehave the moment two teams agree to a
    larger quota (I6). At today's quota of 14 this produces boundaries
    close to that illustrative fixed example anyway."""
    if count <= 0:
        return 0
    if quota <= 0:
        return 3  # defensive: a zero quota with a nonzero count can't happen, but never divide by zero
    if count <= quota / 3:
        return 1
    if count <= 2 * quota / 3:
        return 2
    return 3


def _count_open_neighbours(pos: Position, board: Board, barriers: BarrierSet) -> int:
    """Deliberately duplicated from `training/opponent_policies.py`'s own
    identically-shaped helper, not imported: production code under
    `src/cop/` cannot import `training/` (`test_training_boundary.py`
    enforces this direction too) — same precedent
    `greedy_escape_thief`/`tests/support/greedy_thief_mover.py` already set
    for this exact kind of small, load-bearing repetition."""
    count = 0
    for direction, delta in DELTAS.items():
        if direction == "STAY":
            continue
        neighbour = pos + delta
        if board.in_bounds(neighbour) and not barriers.blocks(neighbour):
            count += 1
    return count


def _bucket_enclosure(open_count: int) -> int:
    """0-4 open orthogonal neighbours -> 3 coarse levels — the raw range is
    already small, so unlike barrier count, little further coarsening is
    needed. 0-1 open: cornered/chokepoint. 2: constrained. 3-4: open."""
    if open_count <= 1:
        return 0
    if open_count == 2:
        return 1
    return 2


def _clamp(value: int, radius: int) -> int:
    """Saturate `value` to `[-radius, radius]` — every displacement beyond
    the radius folds into the same boundary value (see module docstring)."""
    return max(-radius, min(radius, value))


def _bucket_confidence(confidence: float) -> int:
    """Monotonic: a higher confidence never produces a lower bucket index."""
    bucket = 0
    for threshold in _CONFIDENCE_THRESHOLDS:
        if confidence < threshold:
            return bucket
        bucket += 1
    return bucket


def encode_state(
    own_pos: Position,
    target_pos: Position,
    board: Board,
    barriers: BarrierSet,
    *,
    belief_confidence: float = 1.0,
) -> State:
    """Same parameter order as `BrainBase._pick_move` — the encoding is
    computed from exactly what a brain already receives, no extra plumbing
    needed at either training or inference time. `belief_confidence` is
    keyword-only and defaulted so every pre-existing positional call site
    (ground-truth training, `run_local_subgame`) keeps working unchanged —
    see the module docstring."""
    dx = _clamp(target_pos.col - own_pos.col, _CLAMP_RADIUS)
    dy = _clamp(target_pos.row - own_pos.row, _CLAMP_RADIUS)
    bitmask = 0
    for index, direction in enumerate(_BIT_ORDER):
        destination = apply_move(own_pos, direction, board)
        blocked = destination is None or barriers.blocks(destination)
        if blocked:
            bitmask |= 1 << index
    barrier_count_bucket = _bucket_barrier_count(len(barriers.placed), barriers.quota)
    enclosure_bucket = _bucket_enclosure(_count_open_neighbours(target_pos, board, barriers))
    return (
        dx, dy, bitmask, _bucket_confidence(belief_confidence), barrier_count_bucket, enclosure_bucket,
    )
