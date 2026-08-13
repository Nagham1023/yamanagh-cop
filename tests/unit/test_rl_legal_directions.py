"""rl_legal_directions.py: the live legality set, and the backtrack-
avoidance helpers PRD 14 round-2 post-gate added after a real promoted
checkpoint was found oscillating (E, W, E, W...) against a real opponent."""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.reasoning.rl_legal_directions import (
    legal_directions,
    opposite_direction,
    pick_avoiding_backtrack,
    pick_ranked_action_avoiding_backtrack,
)

_BOARD = Board(size=7)


def test_opposite_direction_covers_all_four_orthogonal_pairs():
    assert opposite_direction("N") == "S"
    assert opposite_direction("S") == "N"
    assert opposite_direction("E") == "W"
    assert opposite_direction("W") == "E"


def test_opposite_direction_is_none_for_none_and_for_stay():
    assert opposite_direction(None) is None
    assert opposite_direction("STAY") is None


def test_pick_avoiding_backtrack_with_no_last_direction_just_picks_top_ranked():
    result = pick_avoiding_backtrack(["W", "S"], {"W", "S", "N", "E", "STAY"}, None)
    assert result == "W"


def test_pick_avoiding_backtrack_skips_the_exact_reverse_when_a_better_option_exists():
    result = pick_avoiding_backtrack(["W", "S"], {"W", "S"}, last_direction="E")
    assert result == "S"  # "W" would reverse "E"; "S" doesn't


def test_pick_avoiding_backtrack_falls_back_to_the_reverse_when_its_the_only_legal_option():
    result = pick_avoiding_backtrack(["W"], {"W"}, last_direction="E")
    assert result == "W"


def test_pick_avoiding_backtrack_skips_illegal_entries_regardless_of_backtrack_status():
    result = pick_avoiding_backtrack(["N", "S"], {"S"}, last_direction=None)
    assert result == "S"  # "N" isn't in the legal set at all


def test_pick_avoiding_backtrack_returns_none_when_nothing_is_legal():
    result = pick_avoiding_backtrack(["N", "W"], {"S"}, last_direction=None)
    assert result is None


def test_pick_ranked_action_avoiding_backtrack_a_legal_barrier_wins_immediately():
    own_pos = Position(3, 3)
    barriers = BarrierSet(quota=14)
    # "W" would reverse "E", but the ranked barrier action comes first and
    # is never subject to backtrack-avoidance at all.
    result = pick_ranked_action_avoiding_backtrack(
        ["BARRIER_S", "W"], own_pos, _BOARD, barriers, last_direction="E"
    )
    assert result == "BARRIER_S"


def test_pick_ranked_action_avoiding_backtrack_an_illegal_barrier_falls_through_to_moves():
    own_pos = Position(3, 3)
    barriers = BarrierSet(quota=0)  # quota exhausted -- no barrier can be placed
    result = pick_ranked_action_avoiding_backtrack(
        ["BARRIER_S", "N"], own_pos, _BOARD, barriers, last_direction=None
    )
    assert result == "N"


def test_pick_ranked_action_avoiding_backtrack_applies_the_same_guard_to_moves():
    own_pos = Position(3, 3)
    barriers = BarrierSet(quota=14)
    result = pick_ranked_action_avoiding_backtrack(
        ["W", "S"], own_pos, _BOARD, barriers, last_direction="E"
    )
    assert result == "S"


def test_pick_ranked_action_avoiding_backtrack_returns_none_when_nothing_is_legal():
    own_pos = Position(0, 0)  # corner: N and W are off-board
    barriers = BarrierSet(quota=0)
    result = pick_ranked_action_avoiding_backtrack(
        ["N", "W", "BARRIER_N"], own_pos, _BOARD, barriers, last_direction=None
    )
    assert result is None


def test_legal_directions_always_includes_stay():
    result = legal_directions(Position(0, 0), _BOARD, BarrierSet(quota=0))
    assert "STAY" in result
