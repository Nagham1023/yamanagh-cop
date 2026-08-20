"""escape_area.py tests (PLAN.md Stage 11.4) -- BFS-bounded reachable-area
scorer, the core signal behind the escape-area-aware cop brain."""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.reasoning.escape_area import escape_area


def test_open_board_center_reaches_the_full_manhattan_ball_within_bounds():
    board = Board(size=7)
    barriers = BarrierSet(quota=14)
    center = Position(3, 3)

    area = escape_area(center, board, barriers, max_steps=2)

    # Every cell within Manhattan distance 2 of (3,3) is in-bounds on a 7x7
    # board -- 1 (self) + 4 (distance 1) + 8 (distance 2) = 13.
    assert area == 13


def test_a_wall_directly_reduces_the_reachable_count():
    board = Board(size=7)
    center = Position(3, 3)
    open_barriers = BarrierSet(quota=14)
    open_area = escape_area(center, board, open_barriers, max_steps=2)

    walled = BarrierSet(quota=14)
    walled.placed = {Position(3, 2)}  # directly north of center
    walled_area = escape_area(center, board, walled, max_steps=2)

    assert walled_area < open_area


def test_increasing_max_steps_never_decreases_the_reachable_count():
    board = Board(size=7)
    barriers = BarrierSet(quota=14)
    center = Position(3, 3)

    shallow = escape_area(center, board, barriers, max_steps=1)
    deep = escape_area(center, board, barriers, max_steps=3)

    assert deep >= shallow


def test_a_corner_has_a_strictly_smaller_area_than_the_center_at_the_same_depth():
    board = Board(size=7)
    barriers = BarrierSet(quota=14)

    corner_area = escape_area(Position(0, 0), board, barriers, max_steps=3)
    center_area = escape_area(Position(3, 3), board, barriers, max_steps=3)

    assert corner_area < center_area


def test_fully_enclosing_a_cell_leaves_only_itself_reachable():
    board = Board(size=7)
    barriers = BarrierSet(quota=14)
    center = Position(3, 3)
    barriers.placed = {Position(2, 3), Position(4, 3), Position(3, 2), Position(3, 4)}

    area = escape_area(center, board, barriers, max_steps=5)

    assert area == 1
