"""Curriculum sparring opponents: always legal, and stage 1 actually prefers
more open cells (the property PRD-3's own framing names)."""

from __future__ import annotations

import random

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.domain.movement import apply_move
from training.opponent_policies import (
    greedy_escape_thief,
    lookahead_evader_thief,
    make_random_walk_thief,
)

_BOARD = Board(size=7)


def test_random_walk_thief_always_returns_a_legal_move():
    rng = random.Random(20260812)
    mover = make_random_walk_thief(rng)
    barriers = BarrierSet(quota=14)
    for _ in range(200):
        pos = Position(rng.randrange(7), rng.randrange(7))
        direction = mover(pos, _BOARD, barriers)
        assert direction == "STAY" or apply_move(pos, direction, _BOARD) is not None


def test_random_walk_thief_is_deterministic_for_a_given_seeded_rng():
    barriers = BarrierSet(quota=14)
    first = make_random_walk_thief(random.Random(1))(Position(3, 3), _BOARD, barriers)
    second = make_random_walk_thief(random.Random(1))(Position(3, 3), _BOARD, barriers)
    assert first == second


def test_random_walk_thief_stays_when_fully_boxed_in():
    rng = random.Random(0)
    mover = make_random_walk_thief(rng)
    corner = Position(0, 0)
    barriers = BarrierSet(quota=14, placed={Position(1, 0), Position(0, 1)})
    assert mover(corner, _BOARD, barriers) == "STAY"


def test_greedy_escape_thief_always_returns_a_legal_move():
    rng = random.Random(20260812)
    barriers = BarrierSet(quota=14)
    for _ in range(200):
        pos = Position(rng.randrange(7), rng.randrange(7))
        direction = greedy_escape_thief(pos, _BOARD, barriers)
        assert direction == "STAY" or apply_move(pos, direction, _BOARD) is not None


def test_greedy_escape_thief_prefers_the_neighbour_with_more_open_escape_routes():
    # From (0,1): candidates are N=(0,0) [2 open neighbours], S=(0,2) [2, one
    # blocked], E=(1,1) [3, one blocked] — E is the unique, unambiguous best.
    barriers = BarrierSet(quota=14, placed={Position(1, 2)})
    direction = greedy_escape_thief(Position(0, 1), _BOARD, barriers)
    assert direction == "E"


def test_greedy_escape_thief_stays_when_fully_boxed_in():
    corner = Position(0, 0)
    barriers = BarrierSet(quota=14, placed={Position(1, 0), Position(0, 1)})
    assert greedy_escape_thief(corner, _BOARD, barriers) == "STAY"


def test_lookahead_evader_thief_always_returns_a_legal_move():
    rng = random.Random(20260812)
    barriers = BarrierSet(quota=14)
    for _ in range(200):
        pos = Position(rng.randrange(7), rng.randrange(7))
        direction = lookahead_evader_thief(pos, _BOARD, barriers)
        assert direction == "STAY" or apply_move(pos, direction, _BOARD) is not None


def test_lookahead_evader_thief_is_deterministic():
    barriers = BarrierSet(quota=14, placed={Position(1, 2)})
    first = lookahead_evader_thief(Position(0, 1), _BOARD, barriers)
    second = lookahead_evader_thief(Position(0, 1), _BOARD, barriers)
    assert first == second


def test_lookahead_evader_thief_stays_when_fully_boxed_in():
    corner = Position(0, 0)
    barriers = BarrierSet(quota=14, placed={Position(1, 0), Position(0, 1)})
    assert lookahead_evader_thief(corner, _BOARD, barriers) == "STAY"


def test_lookahead_evader_thief_genuinely_looks_two_ply_deep_not_just_one():
    """A real, found-not-constructed-by-hand disagreement: greedy_escape_thief
    (1-ply) and lookahead_evader_thief (2-ply) pick *different* legal
    directions from the same state — proving the deeper lookahead changes
    the actual decision, not just its tie-breaking."""
    pos = Position(2, 5)
    barriers = BarrierSet(
        quota=14,
        placed={
            Position(1, 2), Position(0, 4), Position(5, 4),
            Position(3, 3), Position(2, 6), Position(1, 0),
        },
    )
    assert greedy_escape_thief(pos, _BOARD, barriers) == "N"
    assert lookahead_evader_thief(pos, _BOARD, barriers) == "E"
