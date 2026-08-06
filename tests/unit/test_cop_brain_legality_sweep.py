"""Property-based legality sweep: hand-written rejection tests cover the
cases we thought of; from PRD 5 onward an illegal move is a technical loss
the opponent enforces, so this covers the ones we didn't. Uses stdlib
`random` with a fixed seed (no new test dependency) — deterministic and
reproducible, not fuzzing.
"""

from __future__ import annotations

import random

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.domain.movement import apply_move
from cop.reasoning.brain_base import Move, PlaceBarrier
from cop.reasoning.cop_brain import CopBrain

_SEED = 20260806
_ITERATIONS = 500
_BOARD_SIZE = 7


def _random_position(rng: random.Random, board_size: int) -> Position:
    return Position(rng.randrange(board_size), rng.randrange(board_size))


def _random_barrier_set(rng: random.Random, board_size: int, exclude: set[Position]) -> BarrierSet:
    quota = rng.randint(0, 14)
    candidates = [
        Position(col, row)
        for col in range(board_size)
        for row in range(board_size)
        if Position(col, row) not in exclude
    ]
    rng.shuffle(candidates)
    placed_count = rng.randint(0, quota)
    return BarrierSet(quota=quota, placed=set(candidates[:placed_count]))


def test_decide_move_output_is_always_legal_over_randomized_states():
    rng = random.Random(_SEED)
    brain = CopBrain()
    board = Board(size=_BOARD_SIZE)

    for i in range(_ITERATIONS):
        own_pos = _random_position(rng, _BOARD_SIZE)
        target_pos = _random_position(rng, _BOARD_SIZE)
        barriers = _random_barrier_set(rng, _BOARD_SIZE, exclude={own_pos, target_pos})

        action = brain._decide_move(own_pos, target_pos, board, barriers)

        if isinstance(action, Move):
            if action.direction != "STAY":
                destination = apply_move(own_pos, action.direction, board)
                assert destination is not None, (
                    f"iteration {i}: {action} is off-board from {own_pos}"
                )
                assert not barriers.blocks(destination), (
                    f"iteration {i}: {action} moves into a blocked cell {destination}"
                )
        elif isinstance(action, PlaceBarrier):
            assert barriers.can_place(own_pos, action.target, board), (
                f"iteration {i}: {action} is illegal from {own_pos} "
                f"(quota={barriers.quota}, placed={len(barriers.placed)})"
            )
        else:
            raise AssertionError(f"iteration {i}: unrecognized action type {action!r}")
