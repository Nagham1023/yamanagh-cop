"""`claims_capture()` (PRD 8 Design Question 1): the honest, belief-only
capture trigger — the cop can only ever claim its own believed cell, never
a verified one.
"""

from __future__ import annotations

from cop.domain.board import Position
from cop.reasoning.brain_base import Move, PlaceBarrier
from cop.reasoning.state import claims_capture


def test_a_move_landing_exactly_on_the_belief_target_claims_it():
    result = claims_capture(
        Move(direction="E"), Position(0, 0), Position(1, 0), target_pos=Position(1, 0)
    )
    assert result == Position(1, 0)


def test_a_move_landing_elsewhere_claims_nothing():
    result = claims_capture(
        Move(direction="E"), Position(0, 0), Position(1, 0), target_pos=Position(5, 5)
    )
    assert result is None


def test_a_barrier_placed_exactly_on_the_belief_target_claims_it():
    result = claims_capture(
        PlaceBarrier(target=Position(2, 2)), Position(1, 2), Position(1, 2), target_pos=Position(2, 2)
    )
    assert result == Position(2, 2)


def test_a_barrier_placed_elsewhere_claims_nothing():
    result = claims_capture(
        PlaceBarrier(target=Position(2, 2)), Position(1, 2), Position(1, 2), target_pos=Position(5, 5)
    )
    assert result is None


def test_own_pos_before_never_enters_the_move_comparison():
    # own_pos_before happens to equal target_pos, but the move lands
    # elsewhere — must not trigger on the *starting* position matching.
    result = claims_capture(
        Move(direction="E"), Position(1, 0), Position(2, 0), target_pos=Position(1, 0)
    )
    assert result is None
