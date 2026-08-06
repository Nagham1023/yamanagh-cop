"""tests/support/greedy_thief_mover.py: prefers the neighbour with more escape routes."""

from __future__ import annotations

from greedy_thief_mover import greedy_thief_move

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position


def test_prefers_the_neighbour_with_more_open_escape_routes():
    board = Board(size=7)
    barriers = BarrierSet(quota=14)
    # From the left edge (0, 3): N=(0,2) and S=(0,4) each have 3 open
    # neighbours (one side is off-board); E=(1,3) is interior with 4.
    move = greedy_thief_move(Position(0, 3), board, barriers)

    assert move == "E"
