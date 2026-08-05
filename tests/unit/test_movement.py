"""Movement legality (rules 13, 14): orthogonal steps and stay accepted, everything else rejected."""

from __future__ import annotations

import pytest

from cop.domain.board import Board, Position
from cop.domain.movement import apply_move, is_legal_direction

BOARD = Board(size=7)


@pytest.mark.parametrize("direction", ["N", "S", "E", "W", "STAY"])
def test_all_five_fixed_directions_are_legal(direction):
    assert is_legal_direction(direction) is True


@pytest.mark.parametrize("direction", ["NE", "NW", "SE", "SW", "UP", "", "north"])
def test_diagonal_and_unknown_directions_are_rejected(direction):
    assert is_legal_direction(direction) is False


def test_orthogonal_move_lands_on_the_expected_cell():
    destination = apply_move(Position(3, 3), "E", BOARD)
    assert destination == Position(4, 3)


def test_stay_does_not_change_position():
    destination = apply_move(Position(3, 3), "STAY", BOARD)
    assert destination == Position(3, 3)


def test_diagonal_move_is_rejected():
    assert apply_move(Position(3, 3), "NE", BOARD) is None


def test_move_off_the_board_edge_is_rejected():
    assert apply_move(Position(0, 0), "W", BOARD) is None
    assert apply_move(Position(0, 0), "N", BOARD) is None
    assert apply_move(Position(6, 6), "E", BOARD) is None
