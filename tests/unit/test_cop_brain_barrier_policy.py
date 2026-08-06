"""CopBrain._decide_move: the barrier choice — place when useful and safe, else move."""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.reasoning.brain_base import Move, PlaceBarrier
from cop.reasoning.cop_brain import CopBrain


def test_decide_move_places_a_barrier_adjacent_to_the_cop_that_restricts_the_target():
    brain = CopBrain()
    board = Board(size=7)
    barriers = BarrierSet(quota=14)
    # cop at (4, 4), target diagonally at (3, 3): both (4, 3) and (3, 4) are
    # adjacent to the cop AND to the target. (4, 3) wins the tie-break as
    # the cop's own preferred step, so it's excluded from consideration
    # (found via reproduction: barricading your own best path traps the
    # heuristic in a permanent oscillation) — (3, 4) remains: still useful,
    # still safe, and not the cop's own path.
    action = brain._decide_move(Position(4, 4), Position(3, 3), board, barriers)

    assert action == PlaceBarrier(target=Position(3, 4))


def test_decide_move_never_places_over_quota():
    brain = CopBrain()
    board = Board(size=7)
    barriers = BarrierSet(quota=0)  # quota already exhausted

    action = brain._decide_move(Position(3, 3), Position(3, 1), board, barriers)

    assert isinstance(action, Move)


def test_decide_move_never_walls_the_cop_off_from_itself():
    brain = CopBrain()
    board = Board(size=7)
    barriers = BarrierSet(quota=14)
    cop = Position(3, 3)
    # Pre-block 3 of the cop's 4 neighbours, leaving only S = (3, 4) open.
    barriers.place(cop, Position(3, 2), board)  # N
    barriers.place(cop, Position(4, 3), board)  # E
    barriers.place(cop, Position(2, 3), board)  # W
    # The target sits right past the cop's one remaining open neighbour, so
    # barricading it *would* restrict the target — but it's also the cop's
    # last legal move, so it must be rejected.
    target = Position(3, 5)

    action = brain._decide_move(cop, target, board, barriers)

    assert isinstance(action, Move), "must not place the self-trapping barrier at (3, 4)"


def test_decide_move_never_barricades_its_own_preferred_next_step():
    # Regression: found by actually running a static-target pursuit end to
    # end (reasoning/subgame.py work) — cop at (3, 1) chasing (3, 3) placed
    # a barrier at (3, 2), its own single best next step, and then
    # oscillated between (3, 0) and (3, 1) forever since the greedy
    # heuristic has no lookahead to route around its own obstacle.
    brain = CopBrain()
    board = Board(size=7)
    barriers = BarrierSet(quota=14)

    action = brain._decide_move(Position(3, 1), Position(3, 3), board, barriers)

    assert action == Move(direction="S")


def test_decide_move_falls_back_to_move_when_no_placement_restricts_the_target():
    brain = CopBrain()
    board = Board(size=7)
    barriers = BarrierSet(quota=14)
    # Target far away — none of the cop's 4 neighbours are also the target's.
    action = brain._decide_move(Position(0, 0), Position(6, 6), board, barriers)

    assert isinstance(action, Move)
