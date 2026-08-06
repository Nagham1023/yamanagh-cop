"""CopBrain._pick_move: Manhattan descent, deterministic tie-break, never illegal."""

from __future__ import annotations

import pytest

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.reasoning.cop_brain import CopBrain


@pytest.mark.parametrize(
    ("own", "target", "expected"),
    [
        (Position(3, 3), Position(3, 0), "N"),
        (Position(3, 3), Position(3, 6), "S"),
        (Position(3, 3), Position(6, 3), "E"),
        (Position(3, 3), Position(0, 3), "W"),
    ],
)
def test_pick_move_closes_distance_toward_an_axis_aligned_target(own, target, expected):
    brain = CopBrain()
    board = Board(size=7)
    barriers = BarrierSet(quota=14)

    assert brain._pick_move(own, target, board, barriers) == expected


def test_pick_move_breaks_ties_deterministically_for_a_diagonal_target():
    brain = CopBrain()
    board = Board(size=7)
    barriers = BarrierSet(quota=14)

    first = brain._pick_move(Position(0, 0), Position(2, 2), board, barriers)
    second = brain._pick_move(Position(0, 0), Position(2, 2), board, barriers)

    assert first == second == "E"  # E and S tie at distance 3; E precedes S in tie-break order


def test_pick_move_avoids_a_barrier_blocked_cell_even_if_it_looks_shortest():
    brain = CopBrain()
    board = Board(size=7)
    barriers = BarrierSet(quota=14)
    barriers.place(Position(0, 0), Position(1, 0), board)  # block the "obviously shortest" E step

    move = brain._pick_move(Position(0, 0), Position(5, 0), board, barriers)

    assert move != "E"
    assert move == "S"  # the only remaining legal candidate


def test_pick_move_never_proposes_off_board_and_falls_back_to_stay_when_fully_boxed_in():
    brain = CopBrain()
    board = Board(size=7)
    barriers = BarrierSet(quota=14)
    # (0, 0) is a corner: N and W are structurally off-board. Block E and S too.
    barriers.place(Position(0, 0), Position(1, 0), board)
    barriers.place(Position(0, 0), Position(0, 1), board)

    move = brain._pick_move(Position(0, 0), Position(5, 5), board, barriers)

    assert move == "STAY"
