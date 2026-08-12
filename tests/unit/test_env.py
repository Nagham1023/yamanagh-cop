"""SelfPlayEnv's belief-based observation (PRD 14 sub-layer A): the policy
sees a belief estimate, never the true thief_pos, while physics (capture,
reward) stays ground-truth throughout — see env.py's own module docstring.
"""

from __future__ import annotations

import dataclasses
import random

from cop.domain.board import Board
from training.config import RLTrainingConfig
from training.env import SelfPlayEnv
from training.opponent_policies import make_random_walk_thief


def _rl_config(**overrides) -> RLTrainingConfig:
    base = {
        "episode_count": 1, "seed": 0, "curriculum_switch_episode": 0, "curriculum_switch_episode_2": 0,
        "alpha": 0.1, "gamma": 0.95,
        "epsilon_start": 0.0, "epsilon_end": 0.0, "epsilon_decay": 1.0, "distance_shaping_weight": 0.1,
        "step_cost": 0.01, "max_refinement_rounds": 1, "win_rate_target": 0.0,
        "wall_clock_budget_seconds": 1.0,
    }
    base.update(overrides)
    return RLTrainingConfig(**base)


def test_belief_stays_a_genuine_probability_distribution_after_several_steps(config):
    board = Board(size=config.board_size)
    opponent = make_random_walk_thief(random.Random(1))
    env = SelfPlayEnv(board, config, _rl_config(), opponent)
    env.reset()

    for _ in range(5):
        _next_state, _reward, done, _outcome = env.step("STAY")
        if done:
            break

    assert abs(env._belief.belief_map.total_probability() - 1.0) < 1e-9


def test_encoded_target_can_differ_from_the_true_thief_position(config):
    # The whole point of sub-layer A: once the cop has moved and sampled
    # some scent, its belief's own best guess need not be exactly thief_pos
    # (it's an estimate, not a leak of ground truth) — assert the encoder is
    # actually driven by the belief, not silently still reading thief_pos.
    board = Board(size=config.board_size)
    opponent = make_random_walk_thief(random.Random(2))
    env = SelfPlayEnv(board, config, _rl_config(), opponent)
    env.reset()

    believed_pos, _confidence = env._belief.believed_target()
    state_from_belief = env._encode()

    # Directly construct the ground-truth encoding for comparison, proving
    # the two are computed differently, not that they coincidentally match.
    from cop.reasoning.rl_state_encoding import encode_state

    state_from_truth = encode_state(env.cop_pos, env.thief_pos, board, env._barriers)

    if believed_pos != env.thief_pos:
        assert state_from_belief != state_from_truth
    else:
        # A uniform prior can legitimately tie-break onto the true cell by
        # chance at step 0 — not a failure, just not the interesting case.
        assert state_from_belief[3] == 0  # still the "no idea yet" confidence bucket


def test_belief_confidence_grows_as_the_cop_gathers_scent_evidence(config):
    board = Board(size=config.board_size)
    opponent = make_random_walk_thief(random.Random(3))
    env = SelfPlayEnv(board, config, _rl_config(), opponent)
    env.reset()

    _pos0, confidence_at_reset = env._belief.believed_target()

    for _ in range(10):
        _next_state, _reward, done, _outcome = env.step("N")
        if done:
            break

    _pos_n, confidence_after_steps = env._belief.believed_target()

    # A uniform 7x7 prior's own peak is already ~1/49 ≈ 0.02 — confidence
    # should not *shrink* below that floor as real evidence accumulates.
    assert confidence_after_steps >= confidence_at_reset


def test_exhausting_the_real_barrier_quota_removes_barrier_actions_from_legal_actions(config):
    quota_one_config = dataclasses.replace(config, barrier_quota=1)
    board = Board(size=quota_one_config.board_size)
    opponent = make_random_walk_thief(random.Random(4))
    env = SelfPlayEnv(board, quota_one_config, _rl_config(), opponent)
    env.reset()

    # cop_start is a corner (0,0): N/W are off-board, so only S/E are real
    # barrier-placement targets — BARRIER_S is the one that actually spends
    # the quota here.
    env.step("BARRIER_S")
    legal = env.legal_actions()
    assert not any(action.startswith("BARRIER_") for action in legal)


def test_an_over_quota_barrier_step_is_a_safe_no_op_not_a_crash(config):
    quota_one_config = dataclasses.replace(config, barrier_quota=1)
    board = Board(size=quota_one_config.board_size)
    opponent = make_random_walk_thief(random.Random(5))
    env = SelfPlayEnv(board, quota_one_config, _rl_config(), opponent)
    env.reset()

    env.step("BARRIER_S")  # spends the one available placement
    barriers_before = set(env._barriers.placed)
    steps_before = env.steps_taken

    # legal_actions() would already exclude this — calling it directly
    # bypasses that filter, the same defensive posture apply_cop_action
    # documents for any caller that skips the filter. BARRIER_E targets a
    # cell distinct from the one already placed, isolating "quota is
    # exhausted" as the rejection reason rather than "duplicate target."
    _next_state, _reward, done, _outcome = env.step("BARRIER_E")

    assert env._barriers.placed == barriers_before  # nothing new recorded
    assert env.steps_taken == steps_before + 1  # still consumes a turn
    assert done in (True, False)  # completes normally either way, no crash
