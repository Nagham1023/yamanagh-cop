"""WeightedRLCopBrain: routes each decision to RLCopBrain with probability
`rl_weight` (default 0.9), CopBrain otherwise. See weighted_cop_brain.py's
own module docstring for why (the real, live oscillation bug this exists
to fix).

Mirrors test_hybrid_cop_brain.py's `_disagreement_checkpoint` pattern: a
checkpoint that strongly prefers a *different* direction than CopBrain's
own tie-break, so routing can be proven by which direction actually comes
back, not just by inspecting private attributes.
"""

from __future__ import annotations

import random

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.domain.movement import apply_move
from cop.reasoning.brain_base import Move, PlaceBarrier
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.rl_checkpoint import save_checkpoint
from cop.reasoning.rl_state_encoding import encode_state
from cop.reasoning.weighted_cop_brain import WeightedRLCopBrain

_BOARD = Board(size=7)
_SEED = 20260814
_ITERATIONS = 500


def _disagreement_checkpoint(tmp_path):
    """own_pos=(0,0), target_pos=(3,3): CopBrain's greedy heuristic ties
    between "E"/"S" and picks "E" first (_TIE_BREAK_ORDER). The Q-table
    strongly prefers "S" instead, so a genuine, checkable disagreement
    exists between the two delegates."""
    own_pos, target_pos = Position(0, 0), Position(3, 3)
    barriers = BarrierSet(quota=14)
    state = encode_state(own_pos, target_pos, _BOARD, barriers, belief_entropy=0.0)
    path = tmp_path / "checkpoint.json"
    save_checkpoint(path, {state: {"S": 99.0, "E": 1.0}})
    return path, own_pos, target_pos, barriers


def test_default_weight_is_point_nine():
    assert WeightedRLCopBrain()._rl_weight == 0.9


def test_random_draw_below_the_weight_always_routes_to_rl(tmp_path):
    checkpoint_path, own_pos, target_pos, barriers = _disagreement_checkpoint(tmp_path)
    brain = WeightedRLCopBrain(checkpoint_path=checkpoint_path, random_source=lambda: 0.0)
    assert brain._decide_move(own_pos, target_pos, _BOARD, barriers) == Move(direction="S")


def test_random_draw_at_or_above_the_weight_always_routes_to_the_heuristic(tmp_path):
    # Boundary/rejection case: a draw exactly at rl_weight must NOT count as
    # "below" it (strict <), same convention _rejected_for_new_timing_fields
    # and bucket_entropy already use elsewhere in this repo.
    checkpoint_path, own_pos, target_pos, barriers = _disagreement_checkpoint(tmp_path)
    brain = WeightedRLCopBrain(checkpoint_path=checkpoint_path, random_source=lambda: 0.9)
    assert brain._decide_move(own_pos, target_pos, _BOARD, barriers) == Move(direction="E")


def test_random_draw_just_above_zero_still_routes_to_the_heuristic_at_zero_weight(tmp_path):
    checkpoint_path, own_pos, target_pos, barriers = _disagreement_checkpoint(tmp_path)
    brain = WeightedRLCopBrain(
        checkpoint_path=checkpoint_path, rl_weight=0.0, random_source=lambda: 0.0001
    )
    assert brain._decide_move(own_pos, target_pos, _BOARD, barriers) == Move(direction="E")


def test_rl_weight_of_one_always_routes_to_rl_regardless_of_draw(tmp_path):
    checkpoint_path, own_pos, target_pos, barriers = _disagreement_checkpoint(tmp_path)
    brain = WeightedRLCopBrain(
        checkpoint_path=checkpoint_path, rl_weight=1.0, random_source=lambda: 0.9999
    )
    assert brain._decide_move(own_pos, target_pos, _BOARD, barriers) == Move(direction="S")


def test_a_fresh_draw_happens_every_call_not_once_per_game(tmp_path):
    checkpoint_path, own_pos, target_pos, barriers = _disagreement_checkpoint(tmp_path)
    draws = iter([0.0, 0.99])
    brain = WeightedRLCopBrain(checkpoint_path=checkpoint_path, random_source=lambda: next(draws))
    assert brain._decide_move(own_pos, target_pos, _BOARD, barriers) == Move(direction="S")
    assert brain._decide_move(own_pos, target_pos, _BOARD, barriers) == Move(direction="E")


def test_zero_arg_construction_does_not_raise():
    # cli_peer_build.py's real call shape: brain_cls() with no arguments.
    WeightedRLCopBrain()


def test_a_missing_checkpoint_falls_back_to_cop_brain_even_when_routed_to_rl(tmp_path):
    own_pos, target_pos = Position(0, 0), Position(3, 3)
    barriers = BarrierSet(quota=14)
    brain = WeightedRLCopBrain(
        checkpoint_path=tmp_path / "does_not_exist.json", random_source=lambda: 0.0
    )
    baseline = CopBrain()
    assert brain._decide_move(own_pos, target_pos, _BOARD, barriers) == baseline._decide_move(
        own_pos, target_pos, _BOARD, barriers
    )


def test_decide_move_output_is_always_legal_across_both_delegates(tmp_path):
    rng = random.Random(_SEED)
    board = Board(size=7)
    action_pool = ("N", "E", "S", "W", "STAY", "BARRIER_N", "BARRIER_E", "BARRIER_S", "BARRIER_W")

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
        brain = WeightedRLCopBrain(checkpoint_path=checkpoint_path, random_source=rng.random)
        own_pos = Position(rng.randrange(7), rng.randrange(7))
        target_pos = Position(rng.randrange(7), rng.randrange(7))
        quota = rng.randint(0, 14)
        candidates = [
            Position(c, r) for c in range(7) for r in range(7) if Position(c, r) != own_pos
        ]
        rng.shuffle(candidates)
        barriers = BarrierSet(quota=quota, placed=set(candidates[: rng.randint(0, quota)]))

        action = brain._decide_move(own_pos, target_pos, board, barriers)
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


def test_over_many_draws_the_real_random_source_lands_near_the_configured_weight():
    # Not a routing-correctness test (those are exact, above) — a sanity
    # check that plugging in the real random.random (the production default)
    # actually produces roughly a 90/10 split, not some inverted or
    # off-by-one comparison that happens to pass the exact-value tests above.
    brain = WeightedRLCopBrain(random_source=random.Random(_SEED).random)
    rl_hits = sum(1 for _ in range(2000) if brain._active_brain() is brain._rl_brain)
    assert 1700 < rl_hits < 1900  # ~90% of 2000, generous band against RNG noise
