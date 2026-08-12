"""RLCopBrain: Q-table-first, CopBrain-heuristic fallback, always legal."""

from __future__ import annotations

import random

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.domain.movement import apply_move
from cop.reasoning.brain_base import Move, PlaceBarrier
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


def test_an_unvisited_barrier_adjacent_state_still_falls_back_to_the_heuristic(tmp_path):
    """General case, re-verified post sub-layer B: an empty/miss table
    falls back correctly (now via _decide_move, including the barrier
    choice) regardless of whether the state happens to be barrier-adjacent."""
    own_pos, target_pos = Position(3, 3), Position(5, 5)
    blocked = BarrierSet(quota=14, placed={Position(3, 2)})
    save_checkpoint(tmp_path / "checkpoint.json", {})  # empty table
    brain = RLCopBrain(checkpoint_path=tmp_path / "checkpoint.json")
    baseline = CopBrain()
    assert brain._decide_move(own_pos, target_pos, _BOARD, blocked) == baseline._decide_move(
        own_pos, target_pos, _BOARD, blocked
    )


def test_a_visited_barrier_adjacent_state_is_now_read_from_the_table_not_blanket_skipped(tmp_path):
    """PRD 14 sub-layer B reverses the premise the old version of this test
    checked: training used to never place a barrier, so any state with a
    nonzero bitmask was *guaranteed* to miss the table. Now that
    `training/env.py::SelfPlayEnv` places barriers for real, a barrier-
    adjacent state can genuinely be visited — and once it is, `RLCopBrain`
    must actually read it, not treat "barrier nearby" as an automatic miss.
    A premise invalidation, not a silent diff — called out explicitly."""
    own_pos, target_pos = Position(3, 3), Position(5, 5)
    blocked = BarrierSet(quota=14, placed={Position(3, 2)})  # a real barrier north of the cop
    state = encode_state(own_pos, target_pos, _BOARD, blocked)
    assert state[2] != 0  # sanity: this state really does have a nonzero bitmask
    save_checkpoint(tmp_path / "checkpoint.json", {state: {"S": 99.0, "E": 1.0}})
    brain = RLCopBrain(checkpoint_path=tmp_path / "checkpoint.json")
    assert brain._decide_move(own_pos, target_pos, _BOARD, blocked) == Move(direction="S")


def test_a_ranked_barrier_action_becomes_a_place_barrier_when_still_legal(tmp_path):
    own_pos, target_pos = Position(3, 3), Position(0, 0)
    barriers = BarrierSet(quota=14)
    state = encode_state(own_pos, target_pos, _BOARD, barriers)
    save_checkpoint(tmp_path / "checkpoint.json", {state: {"BARRIER_S": 50.0, "N": 1.0}})
    brain = RLCopBrain(checkpoint_path=tmp_path / "checkpoint.json")
    action = brain._decide_move(own_pos, target_pos, _BOARD, barriers)
    assert action == PlaceBarrier(target=Position(3, 4))


def test_a_ranked_barrier_action_that_is_no_longer_legal_is_skipped_not_returned(tmp_path):
    # Quota already exhausted: BARRIER_S can never be placed even though
    # it's ranked highest — the next legal ranked entry must win instead,
    # never the unchecked top-ranked action (rule 25/I7).
    own_pos, target_pos = Position(3, 3), Position(0, 0)
    barriers = BarrierSet(quota=0)
    state = encode_state(own_pos, target_pos, _BOARD, barriers)
    save_checkpoint(tmp_path / "checkpoint.json", {state: {"BARRIER_S": 50.0, "W": 10.0}})
    brain = RLCopBrain(checkpoint_path=tmp_path / "checkpoint.json")
    action = brain._decide_move(own_pos, target_pos, _BOARD, barriers)
    assert action == Move(direction="W")


def test_a_real_prd11_era_v1_checkpoint_falls_back_to_the_heuristic_not_a_crash(tmp_path):
    """PRD 14 sub-layer A bumped the checkpoint format to "v2". A genuine
    old "v1" file on disk (exactly the shape PRD 11/12/13 produced) must
    fail closed into the same safe heuristic fallback as a missing/corrupted
    checkpoint — not crash `RLCopBrain.__init__` — verified against a real
    file, not just re-asserted from `load_checkpoint`'s own docstring."""
    path = tmp_path / "checkpoint.json"
    path.write_text(
        '{"state_encoding_version": "v1", "quantization": null, '
        '"q_values": [{"state": [0, 3, 0], "values": {"S": 4.5}}]}',
        encoding="utf-8",
    )
    brain = RLCopBrain(checkpoint_path=path)
    baseline = CopBrain()
    own_pos, target_pos = Position(0, 0), Position(3, 3)
    barriers = BarrierSet(quota=14)
    assert brain._q_table is None
    assert brain._pick_move(own_pos, target_pos, _BOARD, barriers) == baseline._pick_move(
        own_pos, target_pos, _BOARD, barriers
    )


def test_belief_confidence_provider_is_actually_read_not_decorative(tmp_path):
    """PRD 14 sub-layer A: two checkpoint entries at the *same* own_pos/
    target_pos but different belief-confidence buckets, with deliberately
    different best actions — proves the provider's return value genuinely
    changes which table row gets consulted, not just that the parameter
    exists."""
    own_pos, target_pos = Position(0, 0), Position(3, 3)
    barriers = BarrierSet(quota=14)
    confident_state = encode_state(own_pos, target_pos, _BOARD, barriers, belief_confidence=1.0)
    unsure_state = encode_state(own_pos, target_pos, _BOARD, barriers, belief_confidence=0.05)
    assert confident_state != unsure_state  # sanity: buckets really do differ

    save_checkpoint(
        tmp_path / "checkpoint.json",
        {confident_state: {"S": 99.0, "E": 1.0}, unsure_state: {"E": 99.0, "S": 1.0}},
    )

    confident_brain = RLCopBrain(
        checkpoint_path=tmp_path / "checkpoint.json", belief_confidence_provider=lambda: 1.0
    )
    unsure_brain = RLCopBrain(
        checkpoint_path=tmp_path / "checkpoint.json", belief_confidence_provider=lambda: 0.05
    )
    default_brain = RLCopBrain(checkpoint_path=tmp_path / "checkpoint.json")  # no provider at all

    assert confident_brain._pick_move(own_pos, target_pos, _BOARD, barriers) == "S"
    assert unsure_brain._pick_move(own_pos, target_pos, _BOARD, barriers) == "E"
    # No provider bound -> the documented default (1.0, "confident") -> same as confident_brain.
    assert default_brain._pick_move(own_pos, target_pos, _BOARD, barriers) == "S"


def test_pick_move_output_is_always_legal_over_randomized_states_with_and_without_a_checkpoint(
    tmp_path,
):
    """Same property-based sweep as test_cop_brain_legality_sweep.py, run
    against RLCopBrain both with a populated (partially-covering, partially
    adversarial) checkpoint and with no checkpoint at all. Movement only —
    see the `_decide_move` sweep below for the barrier-inclusive version."""
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


def test_decide_move_output_is_always_legal_including_barrier_choices(tmp_path):
    """PRD 14 sub-layer B: the same property-based legality sweep, now over
    `_decide_move`'s full move-or-barrier action set, so a ranked
    `PlaceBarrier` is checked for legality too, not just movement."""
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
