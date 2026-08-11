"""step_reward: terminal reward reuses Table 17's real score, never reinvented."""

from __future__ import annotations

from cop.domain.scoring import Outcome
from training.config import RLTrainingConfig
from training.reward import step_reward

_RL_CONFIG = RLTrainingConfig(
    episode_count=1,
    seed=0,
    curriculum_switch_episode=0,
    alpha=0.1,
    gamma=0.95,
    epsilon_start=0.0,
    epsilon_end=0.0,
    epsilon_decay=1.0,
    distance_shaping_weight=0.5,
    step_cost=0.2,
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
