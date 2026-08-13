"""BeliefTracker: PRD 14 post-gate follow-up — simulating the thief's own
scent map, the first of the two previously-undocumented-as-simulated
channels this session closes. See belief_tracker.py's own module docstring
for why this is a legitimate completion of an already-honest channel, not
a ground-truth leak.
"""

from __future__ import annotations

import random

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from training.belief_tracker import BeliefTracker

_BOARD = Board(size=7)


def test_repeated_fold_peer_scent_at_a_stationary_thief_concentrates_belief_there(config):
    barriers = BarrierSet(quota=14)
    tracker = BeliefTracker(_BOARD, config, barriers, random.Random(0))
    stationary_thief = Position(5, 5)
    before = tracker.belief_map.probability(stationary_thief)

    for _ in range(10):
        tracker.fold_peer_scent(stationary_thief)

    after = tracker.belief_map.probability(stationary_thief)
    assert after > before  # behaves like a real emitting source, not noise


def test_belief_is_still_the_uniform_prior_before_any_scent_is_folded_in(config):
    barriers = BarrierSet(quota=14)
    tracker = BeliefTracker(_BOARD, config, barriers, random.Random(0))
    uniform = BeliefTracker(_BOARD, config, barriers, random.Random(0)).belief_map  # a fresh, untouched reference
    for cell in uniform._probabilities:
        assert tracker.belief_map.probability(cell) == uniform.probability(cell)


def test_reset_recreates_the_peer_scent_field_not_just_the_cops_own(config):
    barriers = BarrierSet(quota=14)
    tracker = BeliefTracker(_BOARD, config, barriers, random.Random(0))
    tracker.fold_peer_scent(Position(2, 2))
    assert tracker.peer_scent_field.full_field()  # something was deposited

    tracker.reset()
    # A leaked stale field across SelfPlayEnv's per-episode reuse would be a
    # real, silent bug — the field itself must be a fresh object, empty.
    assert tracker.peer_scent_field.full_field() == {}


def test_fold_peer_scent_does_not_touch_the_cops_own_scent_field(config):
    barriers = BarrierSet(quota=14)
    tracker = BeliefTracker(_BOARD, config, barriers, random.Random(0))
    tracker.fold_peer_scent(Position(2, 2))
    assert tracker.scent_field.full_field() == {}  # only the peer field was advanced


def test_a_lie_probability_of_one_deterministically_shifts_belief_away_from_the_true_thief(config):
    barriers = BarrierSet(quota=14)
    tracker = BeliefTracker(_BOARD, config, barriers, random.Random(20260813))
    # interpret_hint resolves "north-west" to the fixed quadrant point
    # (board.size//4, board.size//4) = (1,1) on a 7x7 board, not the literal
    # corner (0,0) — using (1,1) as true_pos means a truthful hint's
    # interpreted focal point round-trips to exactly true_pos itself,
    # avoiding a quadrant-boundary mismatch a corner position would have.
    true_pos = Position(1, 1)
    before = tracker.belief_map.probability(true_pos)

    tracker.fold_synthetic_hint(true_pos, lie_probability=1.0)

    after = tracker.belief_map.probability(true_pos)
    assert after < before  # a forced lie points away from the true region


def test_a_lie_probability_of_zero_deterministically_shifts_belief_toward_the_true_thief(config):
    barriers = BarrierSet(quota=14)
    tracker = BeliefTracker(_BOARD, config, barriers, random.Random(20260813))
    true_pos = Position(1, 1)
    before = tracker.belief_map.probability(true_pos)

    tracker.fold_synthetic_hint(true_pos, lie_probability=0.0)

    after = tracker.belief_map.probability(true_pos)
    assert after > before  # a forced truth points toward the true region


def test_fold_synthetic_hint_fires_every_call_not_throttled(config, monkeypatch):
    barriers = BarrierSet(quota=14)
    tracker = BeliefTracker(_BOARD, config, barriers, random.Random(0))
    calls = []
    monkeypatch.setattr(
        "training.belief_tracker.decide_intent",
        lambda lie_probability, rng: calls.append(1) or False,
    )
    for _ in range(7):
        tracker.fold_synthetic_hint(Position(3, 3), lie_probability=0.3)
    assert len(calls) == 7  # no every_n_steps-style throttle


def test_a_shared_belief_rng_across_two_trackers_continues_the_stream_not_restarts_it(config):
    """The RNG-lifetime regression guard: `train_loop.py` shares one
    `belief_rng` across every episode's own fresh `SelfPlayEnv`/
    `BeliefTracker`. If a future change accidentally reseeded a fresh
    stream per tracker instead, the two trackers below (sharing one `rng`
    object, exactly like two successive training episodes) would draw an
    *identical* intent sequence — the spurious step-index-correlated
    artifact belief_tracker.py's own docstring warns about. They must not."""
    barriers = BarrierSet(quota=14)
    shared_rng = random.Random(20260813)
    intent_calls: list[bool] = []
    import training.belief_tracker as belief_tracker_module

    real_decide_intent = belief_tracker_module.decide_intent

    def _recording_decide_intent(lie_probability, rng):
        result = real_decide_intent(lie_probability, rng)
        intent_calls.append(result)
        return result

    original = belief_tracker_module.decide_intent
    belief_tracker_module.decide_intent = _recording_decide_intent
    try:
        tracker_a = BeliefTracker(_BOARD, config, barriers, shared_rng)
        for i in range(10):
            tracker_a.fold_synthetic_hint(Position(i % 7, 0), lie_probability=0.5)
        first_episode_sequence = list(intent_calls)

        intent_calls.clear()
        tracker_b = BeliefTracker(_BOARD, config, barriers, shared_rng)  # same shared rng object
        for i in range(10):
            tracker_b.fold_synthetic_hint(Position(i % 7, 0), lie_probability=0.5)
        second_episode_sequence = list(intent_calls)
    finally:
        belief_tracker_module.decide_intent = original

    assert first_episode_sequence != second_episode_sequence


def test_believed_targets_matches_believed_target_plus_a_consistent_second_mode(config):
    # PRD 14 round-2 post-gate: believed_targets() must agree with the
    # existing believed_target() on primary/entropy (additive, not a
    # divergent reimplementation), and its own third element must match
    # what belief_map.second_mode(primary) computes independently.
    barriers = BarrierSet(quota=14)
    tracker = BeliefTracker(_BOARD, config, barriers, random.Random(0))
    tracker.belief_map._probabilities = {c: 0.0 for c in tracker.belief_map._probabilities}
    primary = Position(1, 1)
    second_real = Position(5, 5)
    tracker.belief_map._probabilities[primary] = 1.0
    tracker.belief_map._probabilities[second_real] = 0.5

    expected_primary, expected_entropy = tracker.believed_target()
    primary_out, entropy_out, second_out = tracker.believed_targets()

    assert (primary_out, entropy_out) == (expected_primary, expected_entropy)
    assert second_out == tracker.belief_map.second_mode(expected_primary) == second_real


def test_believed_targets_second_mode_is_none_for_a_sharp_unimodal_belief(config):
    barriers = BarrierSet(quota=14)
    tracker = BeliefTracker(_BOARD, config, barriers, random.Random(0))
    primary = tracker.belief_map.most_likely_cell()
    tracker.belief_map._probabilities = {c: 0.0001 for c in tracker.belief_map._probabilities}
    tracker.belief_map._probabilities[primary] = 1.0

    _primary_out, _entropy_out, second_out = tracker.believed_targets()
    assert second_out is None
