"""training/env_actions.py: legal_cop_actions/apply_cop_action — the actual
physics that PRD 14 sub-layer B's barrier actions run through, independent
of SelfPlayEnv's own wiring. Covers two real bugs found and fixed while
building sub-layer B: movement legality silently ignoring barriers, and
barrier placement silently permitting self-entrapment.
"""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from training.env_actions import (
    apply_cop_action,
    barrier_restricts_believed_target,
    legal_cop_actions,
)

_BOARD = Board(size=7)


def test_a_barrier_blocked_direction_is_never_offered_as_a_legal_move():
    # apply_move alone only checks board bounds; barriers must also be
    # checked, or a cop's own barrier looks like an ordinary open move.
    cop_pos = Position(3, 3)
    barriers = BarrierSet(quota=14, placed={Position(3, 2)})  # north of the cop
    legal = legal_cop_actions(cop_pos, _BOARD, barriers)
    assert "N" not in legal


def test_moving_into_a_barrier_blocked_cell_is_a_safe_no_op_not_a_teleport():
    cop_pos = Position(3, 3)
    thief_pos = Position(0, 0)
    barriers = BarrierSet(quota=14, placed={Position(3, 2)})  # north of the cop
    new_pos, captured = apply_cop_action("N", cop_pos, thief_pos, _BOARD, barriers)
    assert new_pos == cop_pos
    assert captured is False


def test_over_quota_barrier_placement_is_a_safe_no_op():
    cop_pos = Position(3, 3)
    thief_pos = Position(0, 0)
    barriers = BarrierSet(quota=0)  # already exhausted
    before = set(barriers.placed)
    new_pos, captured = apply_cop_action("BARRIER_N", cop_pos, thief_pos, _BOARD, barriers)
    assert new_pos == cop_pos
    assert captured is False
    assert barriers.placed == before  # nothing recorded, quota untouched


def test_a_quota_exhausted_barrier_set_offers_no_barrier_actions_at_all():
    cop_pos = Position(3, 3)
    barriers = BarrierSet(quota=1, placed={Position(3, 2)})  # the one placement already spent
    legal = legal_cop_actions(cop_pos, _BOARD, barriers)
    assert not any(action.startswith("BARRIER_") for action in legal)


def test_a_barrier_that_would_seal_the_cops_last_open_move_is_excluded():
    # Cop at (3,3) with N/E/S already walled off: W is the only open move.
    # Placing BARRIER_W would leave zero legal moves (only STAY forever) —
    # found empirically as a real training-time self-entrapment bug.
    cop_pos = Position(3, 3)
    barriers = BarrierSet(
        quota=14, placed={Position(3, 2), Position(4, 3), Position(3, 4)}  # N, E, S
    )
    legal = legal_cop_actions(cop_pos, _BOARD, barriers)
    assert "BARRIER_W" not in legal
    assert "W" in legal  # the move itself must still be offered


def test_a_barrier_that_leaves_at_least_one_other_open_move_is_still_allowed():
    # Same shape as above but only N is walled — placing BARRIER_E still
    # leaves S and W open, so it must not be excluded.
    cop_pos = Position(3, 3)
    barriers = BarrierSet(quota=14, placed={Position(3, 2)})  # N only
    legal = legal_cop_actions(cop_pos, _BOARD, barriers)
    assert "BARRIER_E" in legal
    assert "BARRIER_S" in legal
    assert "BARRIER_W" in legal


def test_barrier_restricts_believed_target_true_when_the_placed_barrier_neighbours_it():
    cop_pos_before = Position(3, 3)
    believed_target = Position(5, 3)  # orthogonally adjacent to BARRIER_E's own target cell, (4,3)
    barriers = BarrierSet(quota=14)
    apply_cop_action("BARRIER_E", cop_pos_before, Position(0, 0), _BOARD, barriers)
    assert barrier_restricts_believed_target(
        "BARRIER_E", cop_pos_before, believed_target, barriers
    ) is True


def test_barrier_restricts_believed_target_false_when_far_from_it():
    cop_pos_before = Position(3, 3)
    believed_target = Position(0, 0)  # nowhere near BARRIER_E's own target, (4,3)
    barriers = BarrierSet(quota=14)
    apply_cop_action("BARRIER_E", cop_pos_before, Position(0, 0), _BOARD, barriers)
    assert barrier_restricts_believed_target(
        "BARRIER_E", cop_pos_before, believed_target, barriers
    ) is False


def test_barrier_restricts_believed_target_false_for_a_non_barrier_action():
    barriers = BarrierSet(quota=14)
    assert barrier_restricts_believed_target("E", Position(3, 3), Position(4, 3), barriers) is False


def test_barrier_restricts_believed_target_false_when_the_placement_never_actually_succeeded():
    # Quota exhausted -> apply_cop_action is a safe no-op, nothing recorded
    # in barriers.placed -> the bonus must not fire for an action that only
    # *looked* like a restricting barrier placement but never happened.
    cop_pos_before = Position(3, 3)
    believed_target = Position(4, 3)
    barriers = BarrierSet(quota=0)
    apply_cop_action("BARRIER_E", cop_pos_before, Position(0, 0), _BOARD, barriers)
    assert barrier_restricts_believed_target(
        "BARRIER_E", cop_pos_before, believed_target, barriers
    ) is False
