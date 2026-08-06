"""reasoning/state.py: applying an Action updates position/steps correctly, or fails loudly."""

from __future__ import annotations

import pytest

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.reasoning.brain_base import Move, PlaceBarrier
from cop.reasoning.state import GameState


def _state() -> GameState:
    return GameState(own_pos=Position(0, 0), target_pos=Position(5, 5), barriers=BarrierSet(quota=14))


def test_applying_a_move_updates_position_and_increments_steps():
    state = _state()
    board = Board(size=7)

    state.apply(Move(direction="E"), board)

    assert state.own_pos == Position(1, 0)
    assert state.steps_taken == 1


def test_applying_a_place_barrier_updates_barriers_and_does_not_move(config):
    state = _state()
    board = Board(size=config.board_size)

    state.apply(PlaceBarrier(target=Position(1, 0)), board)

    assert state.barriers.blocks(Position(1, 0))
    assert state.own_pos == Position(0, 0), "the forgo-move rule: placing a barrier must not also move"
    assert state.steps_taken == 1


def test_applying_an_illegal_move_raises_and_does_not_corrupt_state():
    state = _state()
    board = Board(size=7)

    with pytest.raises(ValueError):
        state.apply(Move(direction="N"), board)  # off-board from (0, 0)

    assert state.own_pos == Position(0, 0)
    assert state.steps_taken == 0


def test_applying_an_illegal_barrier_placement_raises_and_does_not_corrupt_state():
    state = _state()
    board = Board(size=7)

    with pytest.raises(ValueError):
        state.apply(PlaceBarrier(target=Position(5, 5)), board)  # not adjacent to own_pos

    assert state.barriers.placed == set()
    assert state.steps_taken == 0
