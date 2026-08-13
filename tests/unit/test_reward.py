"""step_reward: terminal reward reuses Table 17's real score, never reinvented."""

from __future__ import annotations

from cop.domain.scoring import Outcome
from training.config import RLTrainingConfig
from training.reward import step_reward

_RL_CONFIG = RLTrainingConfig(
    episode_count=1,
    seed=0,
    curriculum_switch_episode=0,
    curriculum_switch_episode_2=0,
    curriculum_switch_episode_3=0,
    alpha=0.1,
    gamma=0.95,
    epsilon_start=0.0,
    epsilon_end=0.0,
    epsilon_decay=1.0,
    distance_shaping_weight=0.5,
    step_cost=0.2,
    barrier_restriction_bonus_weight=0.3,
    synthetic_thief_lie_probability=0.0,
    belief_expected_distance_shaping_weight=0.0,
    max_refinement_rounds=1,
    win_rate_target=0.0,
    wall_clock_budget_seconds=1.0,
)


def test_capture_returns_the_real_configured_capture_score(config):
    reward = step_reward(
        prev_distance=1, new_distance=0, outcome=Outcome.CAPTURE, game_config=config, rl_config=_RL_CONFIG
    )
    assert reward == float(config.score_capture_cop)


def test_survival_returns_the_real_configured_survival_score(config):
    reward = step_reward(
        prev_distance=5, new_distance=5, outcome=Outcome.SURVIVAL, game_config=config, rl_config=_RL_CONFIG
    )
    assert reward == float(config.score_survival_cop)


def test_technical_loss_scores_zero_regardless_of_shaping(config):
    reward = step_reward(
        prev_distance=1, new_distance=9, outcome=Outcome.TECHNICAL_LOSS, game_config=config, rl_config=_RL_CONFIG
    )
    assert reward == 0.0


def test_in_progress_step_shapes_toward_closing_distance_minus_step_cost(config):
    reward = step_reward(
        prev_distance=5, new_distance=3, outcome=None, game_config=config, rl_config=_RL_CONFIG
    )
    assert reward == _RL_CONFIG.distance_shaping_weight * 2 - _RL_CONFIG.step_cost


def test_in_progress_step_moving_away_gives_a_negative_shaping_term(config):
    reward = step_reward(
        prev_distance=3, new_distance=5, outcome=None, game_config=config, rl_config=_RL_CONFIG
    )
    assert reward == _RL_CONFIG.distance_shaping_weight * (-2) - _RL_CONFIG.step_cost


def test_restricts_believed_target_adds_the_configured_bonus(config):
    reward = step_reward(
        prev_distance=5, new_distance=3, outcome=None, game_config=config, rl_config=_RL_CONFIG,
        restricts_believed_target=True,
    )
    without_bonus = step_reward(
        prev_distance=5, new_distance=3, outcome=None, game_config=config, rl_config=_RL_CONFIG,
        restricts_believed_target=False,
    )
    assert reward == without_bonus + _RL_CONFIG.barrier_restriction_bonus_weight


def test_restricts_believed_target_defaults_to_false_and_adds_nothing(config):
    reward = step_reward(
        prev_distance=5, new_distance=3, outcome=None, game_config=config, rl_config=_RL_CONFIG
    )
    assert reward == _RL_CONFIG.distance_shaping_weight * 2 - _RL_CONFIG.step_cost


def test_restricts_believed_target_is_ignored_on_a_terminal_step(config):
    reward = step_reward(
        prev_distance=1, new_distance=0, outcome=Outcome.CAPTURE, game_config=config,
        rl_config=_RL_CONFIG, restricts_believed_target=True,
    )
    assert reward == float(config.score_capture_cop)  # the bonus never leaks into a terminal score


def test_belief_expected_distance_shaping_weight_of_zero_is_byte_identical_to_pre_piece_4(config):
    # "Off means off" — same precedent test barrier_restriction_bonus_weight
    # already has. _RL_CONFIG's belief_expected_distance_shaping_weight is
    # 0.0, so passing wildly different prev/new belief-expected-distance
    # values must not move the reward by even a rounding error, proving the
    # new term is inert at its shipped default regardless of what
    # expected_manhattan_distance() itself returns in a real run.
    reward_with_belief_inputs = step_reward(
        prev_distance=5, new_distance=3, outcome=None, game_config=config, rl_config=_RL_CONFIG,
        prev_expected_distance=40.0, new_expected_distance=0.5,
    )
    reward_without_belief_inputs = step_reward(
        prev_distance=5, new_distance=3, outcome=None, game_config=config, rl_config=_RL_CONFIG,
    )
    assert reward_with_belief_inputs == reward_without_belief_inputs
    assert reward_with_belief_inputs == _RL_CONFIG.distance_shaping_weight * 2 - _RL_CONFIG.step_cost


def test_belief_shaping_can_disagree_in_sign_with_ground_truth_shaping(config):
    # The phantom-chasing risk the module docstring warns about, made
    # concrete: the cop can close real ground-truth distance on the actual
    # thief while its belief (pointed elsewhere, wrongly) says expected
    # distance grew — the two shaping terms pull in opposite directions in
    # the same step. This is exactly why the weight needs a real sweep
    # before shipping nonzero, not proof either term is buggy.
    rl_config = RLTrainingConfig(
        episode_count=1, seed=0, curriculum_switch_episode=0, curriculum_switch_episode_2=0,
        curriculum_switch_episode_3=0,
        alpha=0.1, gamma=0.95, epsilon_start=0.0, epsilon_end=0.0, epsilon_decay=1.0,
        distance_shaping_weight=1.0, step_cost=0.0, barrier_restriction_bonus_weight=0.0,
        synthetic_thief_lie_probability=0.0, belief_expected_distance_shaping_weight=1.0,
        max_refinement_rounds=1, win_rate_target=0.0, wall_clock_budget_seconds=1.0,
    )
    reward = step_reward(
        prev_distance=5, new_distance=3, outcome=None, game_config=config, rl_config=rl_config,
        prev_expected_distance=2.0, new_expected_distance=6.0,
    )
    ground_truth_shaping = rl_config.distance_shaping_weight * (5 - 3)
    belief_shaping = rl_config.belief_expected_distance_shaping_weight * (2.0 - 6.0)

    assert ground_truth_shaping > 0
    assert belief_shaping < 0
    assert reward == ground_truth_shaping + belief_shaping


def test_shaping_term_is_exactly_potential_based_ng_harada_russell_1999(config):
    """Turns reward.py's own module-docstring derivation into a checked
    fact: with Φ(s) = -manhattan_distance, the shaping term must equal
    weight * (Φ(new) - Φ(old)) exactly, for several distance pairs — not
    just "looks like" potential-based shaping."""

    def phi(distance: int) -> float:
        return -distance

    for prev_distance, new_distance in [(5, 3), (3, 5), (10, 0), (0, 0), (7, 7), (1, 9)]:
        reward = step_reward(
            prev_distance=prev_distance, new_distance=new_distance, outcome=None,
            game_config=config, rl_config=_RL_CONFIG,
        )
        expected_shaping = _RL_CONFIG.distance_shaping_weight * (phi(new_distance) - phi(prev_distance))
        assert reward == expected_shaping - _RL_CONFIG.step_cost
