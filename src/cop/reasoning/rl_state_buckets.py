"""Coarsening helpers for `rl_state_encoding.py`'s `State` tuple — split out
once that file grew past the 150-line house cap adding the bimodal fields
(PRD 14 round-2 post-gate). Each function is a pure quantization step from a
raw count to a small bucket index; none of them touch belief or entropy
(that's `belief_entropy_bucket.py`, a separate concern).
"""

from __future__ import annotations

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..domain.movement import DELTAS


def bucket_barrier_count(count: int, quota: int) -> int:
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


def count_open_neighbours(pos: Position, board: Board, barriers: BarrierSet) -> int:
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


def bucket_enclosure(open_count: int) -> int:
    """0-4 open orthogonal neighbours -> 3 coarse levels — the raw range is
    already small, so unlike barrier count, little further coarsening is
    needed. 0-1 open: cornered/chokepoint. 2: constrained. 3-4: open."""
    if open_count <= 1:
        return 0
    if open_count == 2:
        return 1
    return 2


def clamp(value: int, radius: int) -> int:
    """Saturate `value` to `[-radius, radius]` — every displacement beyond
    the radius folds into the same boundary value (see `rl_state_encoding.py`'s
    own module docstring)."""
    return max(-radius, min(radius, value))
