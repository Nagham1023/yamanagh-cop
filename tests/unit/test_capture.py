"""Capture detection (rules 46, 47): coordinate overlap, barrier-on-thief, and encirclement."""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.domain.capture import (
    is_barrier_capture,
    is_coordinate_capture,
    thief_has_no_legal_move,
)

BOARD = Board(size=7)


def test_coordinate_overlap_is_a_capture():
    assert is_coordinate_capture(Position(3, 3), Position(3, 3)) is True


def test_no_overlap_is_not_a_capture():
    assert is_coordinate_capture(Position(2, 2), Position(3, 3)) is False


def test_barrier_dropped_on_thiefs_cell_is_a_capture():
    assert is_barrier_capture(barrier_target=Position(3, 3), thief_pos=Position(3, 3)) is True


def test_barrier_dropped_elsewhere_is_not_a_capture():
    assert is_barrier_capture(barrier_target=Position(2, 2), thief_pos=Position(3, 3)) is False


def test_thief_boxed_in_by_barriers_and_edges_has_no_legal_move():
    # Corner thief at (0,0): the only two orthogonal neighbours are (1,0) and
    # (0,1) — both off the board's edge is impossible here, so barricade both.
    barriers = BarrierSet(quota=14)
    barriers.place(Position(0, 0), Position(1, 0), board=BOARD)
    barriers.place(Position(0, 0), Position(0, 1), board=BOARD)
    assert thief_has_no_legal_move(Position(0, 0), BOARD, barriers) is True


def test_thief_with_one_open_neighbour_has_a_legal_move():
    barriers = BarrierSet(quota=14)
    barriers.place(Position(0, 0), Position(1, 0), board=BOARD)
    # (0, 1) is left open
    assert thief_has_no_legal_move(Position(0, 0), BOARD, barriers) is False


def test_thief_in_the_open_has_a_legal_move():
    barriers = BarrierSet(quota=14)
    assert thief_has_no_legal_move(Position(3, 3), BOARD, barriers) is False
