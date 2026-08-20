"""AdaptiveCopBrain tests (PLAN.md Stage 11.4)."""

from __future__ import annotations

import random

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.reasoning.adaptive_cop_brain import AdaptiveCopBrain
from cop.reasoning.brain_base import Move, PlaceBarrier


def _deterministic_brain(**kwargs) -> AdaptiveCopBrain:
    # A fixed-seed rng makes softmax tie-breaking reproducible for tests
    # that need a single definite answer.
    return AdaptiveCopBrain(rng=random.Random(0), **kwargs)


def test_pick_move_closes_distance_when_no_area_signal_differs():
    board = Board(size=7)
    barriers = BarrierSet(quota=14)
    brain = _deterministic_brain()

    direction = brain._pick_move(Position(0, 0), Position(0, 5), board, barriers)

    # Every direction leaves the thief's pessimistic area identical (open
    # board, no barriers) -- so the tie-break falls to whichever reduces
    # distance to the believed target, which is due south from (0,0).
    assert direction == "S"

    destination = Position(0, 0) + {"S": Position(0, 1)}[direction]
    assert abs(destination.col - 0) + abs(destination.row - 5) < abs(0 - 0) + abs(0 - 5)


def test_pick_move_never_proposes_a_barrier_blocked_cell():
    board = Board(size=7)
    barriers = BarrierSet(quota=14)
    barriers.placed = {Position(0, 1)}  # directly south of the cop
    brain = _deterministic_brain()

    direction = brain._pick_move(Position(0, 0), Position(0, 5), board, barriers)

    assert direction != "S"


def test_pick_move_falls_back_to_stay_when_fully_boxed_in():
    board = Board(size=7)
    barriers = BarrierSet(quota=14)
    barriers.placed = {Position(1, 0), Position(0, 1)}
    brain = _deterministic_brain()

    direction = brain._pick_move(Position(0, 0), Position(3, 3), board, barriers)

    assert direction == "STAY"


def test_decide_move_prefers_a_barrier_that_meaningfully_shrinks_the_thiefs_area():
    # A cop next to a target already boxed toward a corner (south and east
    # walled off) should find one more wall worth its low cost here --
    # closing the pocket rather than taking a redundant step.
    board = Board(size=7)
    barriers = BarrierSet(quota=14)
    barriers.placed = {Position(1, 2), Position(2, 1)}  # south and east of the target
    brain = _deterministic_brain(area_radius=4, area_weight=3.0, barrier_base_cost=1.0)

    action = brain._decide_move(Position(0, 1), Position(1, 1), board, barriers)

    assert isinstance(action, PlaceBarrier)


def test_decide_move_skips_a_barrier_that_isnt_worth_its_cost_on_an_open_board():
    board = Board(size=7)
    barriers = BarrierSet(quota=14)
    brain = _deterministic_brain(area_radius=4, area_weight=3.0, barrier_base_cost=4.0)

    action = brain._decide_move(Position(0, 0), Position(3, 3), board, barriers)

    assert isinstance(action, Move)


def test_softmax_pick_is_deterministic_for_a_single_clear_winner():
    brain = _deterministic_brain()
    scored = [(5.0, "best"), (1.0, "worse"), (0.0, "worst")]

    assert brain._softmax_pick(scored) == "best"


def test_softmax_pick_only_samples_among_genuine_near_ties():
    brain = _deterministic_brain()
    scored = [(5.0, "best"), (5.0, "also_best"), (0.0, "worst")]

    picks = {brain._softmax_pick(scored) for _ in range(30)}

    assert picks <= {"best", "also_best"}
    assert "worst" not in picks


def test_two_brains_with_different_seeds_can_pick_differently_among_ties():
    # The concrete non-determinism guarantee this class exists to add:
    # two independently-seeded brains facing the exact same genuine tie
    # are not guaranteed to agree, unlike a fixed argmax + tie-break.
    scored = [(3.0, "a"), (3.0, "b"), (3.0, "c"), (3.0, "d")]
    picks = set()
    for seed in range(20):
        brain = AdaptiveCopBrain(rng=random.Random(seed))
        picks.add(brain._softmax_pick(scored))

    assert len(picks) > 1
