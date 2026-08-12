"""HybridCopBrain: routes to CopBrain when confident, RLCopBrain when unsure,
reusing the exact _bucket_confidence boundary the Q-table's own encoding
already uses. See hybrid_cop_brain.py's own module docstring for the design.
"""

from __future__ import annotations

import random

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.domain.movement import apply_move
from cop.reasoning.brain_base import Move, PlaceBarrier
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.hybrid_cop_brain import HybridCopBrain
from cop.reasoning.rl_checkpoint import save_checkpoint
from cop.reasoning.rl_cop_brain import RLCopBrain
from cop.reasoning.rl_state_encoding import encode_state

_BOARD = Board(size=7)
_SEED = 20260812
_ITERATIONS = 500


_BUCKET_REPRESENTATIVES = (0.05, 0.2, 0.45, 0.8)  # one confidence value per _bucket_confidence bucket


def _disagreement_checkpoint(tmp_path):
    """own_pos=(0,0), target_pos=(3,3): CopBrain's greedy heuristic ties
    between "E"/"S" and picks "E" first (_TIE_BREAK_ORDER). Force the
    Q-table to strongly prefer the other tied option, "S", so a genuine,
    checkable disagreement exists between the two delegates.

    encode_state's key includes a confidence bucket (the 4th element), so a
    single saved state only matches a query whose confidence falls in the
    same bucket — populate one disagreement entry per bucket so any test's
    confidence value (whichever bucket it lands in) finds it."""
    own_pos, target_pos = Position(0, 0), Position(3, 3)
    barriers = BarrierSet(quota=14)
    q_values = {
        encode_state(own_pos, target_pos, _BOARD, barriers, belief_confidence=c): {
            "S": 99.0, "E": 1.0
        }
        for c in _BUCKET_REPRESENTATIVES
    }
    path = tmp_path / "checkpoint.json"
    save_checkpoint(path, q_values)
    return path, own_pos, target_pos, barriers


def test_no_provider_bound_behaves_exactly_like_cop_brain(tmp_path):
    checkpoint_path, own_pos, target_pos, barriers = _disagreement_checkpoint(tmp_path)
    hybrid = HybridCopBrain(checkpoint_path=checkpoint_path)  # no provider at all
    baseline = CopBrain()
    assert hybrid._decide_move(own_pos, target_pos, _BOARD, barriers) == baseline._decide_move(
        own_pos, target_pos, _BOARD, barriers
    )


def test_the_same_provider_object_is_passed_through_to_the_inner_rl_brain(tmp_path):
    checkpoint_path, *_ = _disagreement_checkpoint(tmp_path)
    provider = lambda: 0.5  # noqa: E731
    hybrid = HybridCopBrain(checkpoint_path=checkpoint_path, belief_confidence_provider=provider)
    assert hybrid._unsure_brain._belief_confidence_provider is provider


def test_confidence_above_threshold_routes_to_cop_brain_not_rl(tmp_path):
    checkpoint_path, own_pos, target_pos, barriers = _disagreement_checkpoint(tmp_path)
    hybrid = HybridCopBrain(checkpoint_path=checkpoint_path, belief_confidence_provider=lambda: 0.9)
    baseline = CopBrain()
    assert hybrid._decide_move(own_pos, target_pos, _BOARD, barriers) == baseline._decide_move(
        own_pos, target_pos, _BOARD, barriers
    )
    assert hybrid._decide_move(own_pos, target_pos, _BOARD, barriers) == Move(direction="E")


def test_confidence_below_threshold_routes_to_rl_cop_brain_not_cop_brain(tmp_path):
    checkpoint_path, own_pos, target_pos, barriers = _disagreement_checkpoint(tmp_path)
    hybrid = HybridCopBrain(checkpoint_path=checkpoint_path, belief_confidence_provider=lambda: 0.1)
    rl_direct = RLCopBrain(checkpoint_path=checkpoint_path, belief_confidence_provider=lambda: 0.1)
    assert hybrid._decide_move(own_pos, target_pos, _BOARD, barriers) == rl_direct._decide_move(
        own_pos, target_pos, _BOARD, barriers
    )
    assert hybrid._decide_move(own_pos, target_pos, _BOARD, barriers) == Move(direction="S")


def test_confidence_of_exactly_the_threshold_value_routes_to_cop_brain(tmp_path):
    checkpoint_path, own_pos, target_pos, barriers = _disagreement_checkpoint(tmp_path)
    hybrid = HybridCopBrain(checkpoint_path=checkpoint_path, belief_confidence_provider=lambda: 0.6)
    assert hybrid._decide_move(own_pos, target_pos, _BOARD, barriers) == Move(direction="E")


def test_confidence_just_below_threshold_routes_to_rl_cop_brain(tmp_path):
    checkpoint_path, own_pos, target_pos, barriers = _disagreement_checkpoint(tmp_path)
    hybrid = HybridCopBrain(
        checkpoint_path=checkpoint_path, belief_confidence_provider=lambda: 0.5999999
    )
    assert hybrid._decide_move(own_pos, target_pos, _BOARD, barriers) == Move(direction="S")


def test_negative_confidence_does_not_crash_and_routes_to_the_least_confident_bucket(tmp_path):
    checkpoint_path, own_pos, target_pos, barriers = _disagreement_checkpoint(tmp_path)
    hybrid = HybridCopBrain(checkpoint_path=checkpoint_path, belief_confidence_provider=lambda: -1.0)
    assert hybrid._decide_move(own_pos, target_pos, _BOARD, barriers) == Move(direction="S")


def test_confidence_above_one_does_not_crash_and_still_routes_to_cop_brain(tmp_path):
    checkpoint_path, own_pos, target_pos, barriers = _disagreement_checkpoint(tmp_path)
    hybrid = HybridCopBrain(checkpoint_path=checkpoint_path, belief_confidence_provider=lambda: 5.0)
    assert hybrid._decide_move(own_pos, target_pos, _BOARD, barriers) == Move(direction="E")


def test_decide_move_output_is_always_legal_across_all_confidence_buckets(tmp_path):
    rng = random.Random(_SEED)
    board = Board(size=7)
    action_pool = ("N", "E", "S", "W", "STAY", "BARRIER_N", "BARRIER_E", "BARRIER_S", "BARRIER_W")
    confidence_pool = (0.05, 0.2, 0.45, 0.8)  # one representative value per bucket

    populated: dict = {}
    for _ in range(50):
        own = Position(rng.randrange(7), rng.randrange(7))
        target = Position(rng.randrange(7), rng.randrange(7))
        barriers = BarrierSet(quota=14)
        state = encode_state(own, target, board, barriers)
        populated[state] = {a: rng.uniform(-5, 5) for a in action_pool}
    checkpoint_path = tmp_path / "checkpoint.json"
    save_checkpoint(checkpoint_path, populated)

    for i in range(_ITERATIONS):
        confidence = confidence_pool[i % len(confidence_pool)]
        hybrid = HybridCopBrain(
            checkpoint_path=checkpoint_path, belief_confidence_provider=lambda c=confidence: c
        )
        own_pos = Position(rng.randrange(7), rng.randrange(7))
        target_pos = Position(rng.randrange(7), rng.randrange(7))
        quota = rng.randint(0, 14)
        candidates = [
            Position(c, r) for c in range(7) for r in range(7) if Position(c, r) != own_pos
        ]
        rng.shuffle(candidates)
        barriers = BarrierSet(quota=quota, placed=set(candidates[: rng.randint(0, quota)]))

        action = hybrid._decide_move(own_pos, target_pos, board, barriers)
        if isinstance(action, Move):
            if action.direction != "STAY":
                destination = apply_move(own_pos, action.direction, board)
                assert destination is not None, f"iteration {i}: {action.direction} is off-board"
                assert not barriers.blocks(destination), (
                    f"iteration {i}: {action.direction} moves into a blocked cell"
                )
        else:
            assert isinstance(action, PlaceBarrier)
            assert barriers.can_place(own_pos, action.target, board), (
                f"iteration {i}: illegal barrier placement at {action.target}"
            )
