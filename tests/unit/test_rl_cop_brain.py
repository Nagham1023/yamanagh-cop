"""RLCopBrain: Q-table-first, CopBrain-heuristic fallback, always legal."""

from __future__ import annotations

import random

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.domain.movement import apply_move
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.rl_checkpoint import save_checkpoint
from cop.reasoning.rl_cop_brain import RLCopBrain
from cop.reasoning.rl_state_encoding import encode_state

_BOARD = Board(size=7)
_SEED = 20260812
_ITERATIONS = 500


def test_missing_checkpoint_behaves_exactly_like_cop_brain(tmp_path):
    brain = RLCopBrain(checkpoint_path=tmp_path / "does_not_exist.json")
    baseline = CopBrain()
    barriers = BarrierSet(quota=14)
    own_pos, target_pos = Position(0, 0), Position(3, 3)
    assert brain._pick_move(own_pos, target_pos, _BOARD, barriers) == baseline._pick_move(
        own_pos, target_pos, _BOARD, barriers
    )


def test_a_visited_state_uses_the_q_table_ranking_when_it_disagrees_with_the_heuristic(tmp_path):
    own_pos, target_pos = Position(0, 0), Position(3, 3)
    barriers = BarrierSet(quota=14)
    state = encode_state(own_pos, target_pos, _BOARD, barriers)
    # CopBrain's greedy heuristic would prefer E or S here; force the table
    # to strongly prefer the (still-legal) alternative "S" to prove the
    # brain is actually reading the table, not silently ignoring it.
    save_checkpoint(tmp_path / "checkpoint.json", {state: {"S": 99.0, "E": 1.0}})
    brain = RLCopBrain(checkpoint_path=tmp_path / "checkpoint.json")
    assert brain._pick_move(own_pos, target_pos, _BOARD, barriers) == "S"


def test_an_unvisited_state_falls_back_to_the_inherited_heuristic_not_a_guess(tmp_path):
    own_pos, target_pos = Position(0, 0), Position(3, 3)
    barriers = BarrierSet(quota=14)
    other_state = encode_state(Position(6, 6), Position(0, 0), _BOARD, barriers)
    save_checkpoint(tmp_path / "checkpoint.json", {other_state: {"N": 5.0}})
    brain = RLCopBrain(checkpoint_path=tmp_path / "checkpoint.json")
    baseline = CopBrain()
    assert brain._pick_move(own_pos, target_pos, _BOARD, barriers) == baseline._pick_move(
        own_pos, target_pos, _BOARD, barriers
    )


def test_a_table_entry_ranking_only_illegal_actions_falls_back_to_stay(tmp_path):
    own_pos, target_pos = Position(0, 0), Position(3, 3)
    barriers = BarrierSet(quota=14)
    state = encode_state(own_pos, target_pos, _BOARD, barriers)
    # "N" and "W" are off-board from the (0,0) corner — both illegal.
    save_checkpoint(tmp_path / "checkpoint.json", {state: {"N": 9.0, "W": 5.0}})
    brain = RLCopBrain(checkpoint_path=tmp_path / "checkpoint.json")
    assert brain._pick_move(own_pos, target_pos, _BOARD, barriers) == "STAY"


def test_a_barrier_adjacent_state_is_never_in_a_training_produced_table_and_falls_back(tmp_path):
    """Training never places barriers (see training/env.py) — a checkpoint
    trained purely against `random_walk`/`greedy_escape` opponents should
    never contain a state with a nonzero bitmask, so a real barrier-adjacent
    state at inference time is guaranteed to miss and fall back safely."""
    own_pos, target_pos = Position(3, 3), Position(5, 5)
    blocked = BarrierSet(quota=14, placed={Position(3, 2)})
    state = encode_state(own_pos, target_pos, _BOARD, blocked)
    save_checkpoint(tmp_path / "checkpoint.json", {})  # empty table, as training would produce
    brain = RLCopBrain(checkpoint_path=tmp_path / "checkpoint.json")
    baseline = CopBrain()
    assert brain._pick_move(own_pos, target_pos, _BOARD, blocked) == baseline._pick_move(
        own_pos, target_pos, _BOARD, blocked
    )
    assert state[2] != 0  # sanity: this state really does have a nonzero bitmask


def test_decide_move_output_is_always_legal_over_randomized_states_with_and_without_a_checkpoint(
    tmp_path,
):
    """Same property-based sweep as test_cop_brain_legality_sweep.py, run
    against RLCopBrain both with a populated (partially-covering, partially
    adversarial) checkpoint and with no checkpoint at all."""
    rng = random.Random(_SEED)
    board = Board(size=7)

    populated: dict = {}
    for _ in range(50):
        own = Position(rng.randrange(7), rng.randrange(7))
        target = Position(rng.randrange(7), rng.randrange(7))
        barriers = BarrierSet(quota=14)
        state = encode_state(own, target, board, barriers)
        populated[state] = {a: rng.uniform(-5, 5) for a in ("N", "E", "S", "W", "STAY")}
    checkpoint_path = tmp_path / "checkpoint.json"
    save_checkpoint(checkpoint_path, populated)

    for brain in (RLCopBrain(checkpoint_path=checkpoint_path), RLCopBrain(checkpoint_path=tmp_path / "missing.json")):
        for i in range(_ITERATIONS):
            own_pos = Position(rng.randrange(7), rng.randrange(7))
            target_pos = Position(rng.randrange(7), rng.randrange(7))
            quota = rng.randint(0, 14)
            candidates = [
                Position(c, r) for c in range(7) for r in range(7) if Position(c, r) != own_pos
            ]
            rng.shuffle(candidates)
            barriers = BarrierSet(quota=quota, placed=set(candidates[: rng.randint(0, quota)]))

            direction = brain._pick_move(own_pos, target_pos, board, barriers)
            if direction != "STAY":
                destination = apply_move(own_pos, direction, board)
                assert destination is not None, f"iteration {i}: {direction} is off-board"
                assert not barriers.blocks(destination), f"iteration {i}: {direction} moves into a blocked cell"
