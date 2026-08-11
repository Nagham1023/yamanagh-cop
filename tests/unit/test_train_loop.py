"""train(): determinism, respects config, and reward trends upward."""

from __future__ import annotations

from training.config import RLTrainingConfig
from training.train_loop import train

_SMALL_CONFIG_KWARGS = {
    "episode_count": 150,
    "seed": 20260812,
    "curriculum_switch_episode": 75,
    "alpha": 0.2,
    "gamma": 0.9,
    "epsilon_start": 1.0,
    "epsilon_end": 0.05,
    "epsilon_decay": 0.97,
    "distance_shaping_weight": 0.1,
    "step_cost": 0.01,
    "max_refinement_rounds": 1,
    "win_rate_target": 0.5,
    "wall_clock_budget_seconds": 60.0,
}


def test_same_seed_produces_an_identical_trained_table(config):
    rl_config = RLTrainingConfig(**_SMALL_CONFIG_KWARGS)
    table_a, metrics_a = train(config, rl_config)
    table_b, metrics_b = train(config, rl_config)
    assert table_a.as_dict() == table_b.as_dict()
    assert metrics_a.reward_history == metrics_b.reward_history


def test_a_different_seed_produces_a_different_trajectory(config):
    rl_config_a = RLTrainingConfig(**_SMALL_CONFIG_KWARGS)
    rl_config_b = RLTrainingConfig(**{**_SMALL_CONFIG_KWARGS, "seed": 999})
    table_a, _ = train(config, rl_config_a)
    table_b, _ = train(config, rl_config_b)
    assert table_a.as_dict() != table_b.as_dict()


def test_metrics_reports_the_configured_episode_count_and_reward_per_episode(config):
    rl_config = RLTrainingConfig(**_SMALL_CONFIG_KWARGS)
    _table, metrics = train(config, rl_config)
    assert metrics.episode_count == rl_config.episode_count
    assert len(metrics.reward_history) == rl_config.episode_count


def test_epsilon_decays_toward_the_floor_and_never_below_it(config):
    rl_config = RLTrainingConfig(**_SMALL_CONFIG_KWARGS)
    _table, metrics = train(config, rl_config)
    assert metrics.final_epsilon >= rl_config.epsilon_end
    assert metrics.final_epsilon < rl_config.epsilon_start


def test_average_reward_in_the_second_half_beats_the_first_half(config):
    """The learning signal itself: reward should trend upward as the table
    fills in, not just run without crashing."""
    rl_config = RLTrainingConfig(
        **{**_SMALL_CONFIG_KWARGS, "episode_count": 400, "curriculum_switch_episode": 200}
    )
    _table, metrics = train(config, rl_config)
    first_half = metrics.reward_history[:200]
    second_half = metrics.reward_history[200:]
    assert sum(second_half) / len(second_half) > sum(first_half) / len(first_half)
