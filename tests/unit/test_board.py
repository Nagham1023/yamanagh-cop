"""Board geometry: bounds checking is the only thing this layer does."""

from __future__ import annotations

from cop.domain.board import Board, Position


def test_center_cell_is_in_bounds():
    board = Board(size=7)
    assert board.in_bounds(Position(3, 3)) is True


def test_corner_cells_are_in_bounds():
    board = Board(size=7)
    assert board.in_bounds(Position(0, 0)) is True
    assert board.in_bounds(Position(6, 6)) is True


def test_off_board_cell_is_rejected():
    board = Board(size=7)
    assert board.in_bounds(Position(7, 0)) is False
    assert board.in_bounds(Position(-1, 3)) is False


def test_position_addition():
    assert Position(2, 2) + Position(1, -1) == Position(3, 1)
