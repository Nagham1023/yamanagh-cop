"""Barrier placement law: quota, adjacency, board bounds, and no-duplicate-placement."""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position

BOARD = Board(size=7)


def test_barrier_on_cops_own_cell_is_legal():
    barriers = BarrierSet(quota=14)
    assert barriers.place(cop_pos=Position(2, 2), target=Position(2, 2), board=BOARD) is True


def test_barrier_on_orthogonally_adjacent_cell_is_legal():
    barriers = BarrierSet(quota=14)
    assert barriers.place(cop_pos=Position(2, 2), target=Position(2, 3), board=BOARD) is True


def test_barrier_two_cells_away_is_rejected():
    barriers = BarrierSet(quota=14)
    assert barriers.place(cop_pos=Position(2, 2), target=Position(2, 4), board=BOARD) is False
    assert barriers.blocks(Position(2, 4)) is False


def test_barrier_off_the_board_edge_is_rejected():
    # TODO1.md #1: a corner cop's off-board neighbour is manhattan-distance 1
    # away but must still be rejected — it used to be accepted and silently
    # burn a barrier from quota.
    barriers = BarrierSet(quota=14)
    corner_cop = Position(0, 0)
    off_board_target = Position(-1, 0)
    assert barriers.place(corner_cop, off_board_target, board=BOARD) is False
    assert len(barriers.placed) == 0


def test_barrier_beyond_quota_is_rejected():
    barriers = BarrierSet(quota=2)
    assert barriers.place(Position(0, 0), Position(0, 0), board=BOARD) is True
    assert barriers.place(Position(0, 0), Position(0, 1), board=BOARD) is True
    # quota exhausted — a third, otherwise-legal placement must fail
    assert barriers.place(Position(0, 0), Position(1, 0), board=BOARD) is False
    assert len(barriers.placed) == 2


def test_duplicate_barrier_placement_is_rejected():
    barriers = BarrierSet(quota=14)
    assert barriers.place(Position(0, 0), Position(0, 0), board=BOARD) is True
    assert barriers.place(Position(0, 0), Position(0, 0), board=BOARD) is False


def test_placed_barrier_blocks_that_cell():
    barriers = BarrierSet(quota=14)
    barriers.place(Position(0, 0), Position(0, 1), board=BOARD)
    assert barriers.blocks(Position(0, 1)) is True
    assert barriers.blocks(Position(1, 1)) is False
