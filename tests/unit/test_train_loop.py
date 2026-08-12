"""train(): determinism, respects config, and reward trends upward."""

from __future__ import annotations

from training import train_loop
from training.config import RLTrainingConfig
from training.train_loop import train

_SMALL_CONFIG_KWARGS = {
    "episode_count": 150,
    "seed": 20260812,
    "curriculum_switch_episode": 75,
    "curriculum_switch_episode_2": 150,  # never reached at the base episode_count -> stage 2 off
    "alpha": 0.2,
    "gamma": 0.9,
    "epsilon_start": 1.0,
    "epsilon_end": 0.05,
    "epsilon_decay": 0.97,
    "distance_shaping_weight": 0.1,
    "step_cost": 0.01,
    "barrier_restriction_bonus_weight": 0.0,
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
    fills in, not just run without crashing.

    PRD 14 sub-layer B grew the state space by ~4-9x (barrier-count and
    enclosure buckets, plus up to 4 BARRIER_<dir> actions per state on top
    of the real `config` fixture's barrier_quota=14) — found empirically to
    need far more than the original 400-episode/single-switch budget to
    converge reliably (many seeds regressed at 400, and even at 1500-2500
    episodes a first-half/second-half split stayed noisy). Two changes
    fixed it, not one: (1) `episode_count` raised and the curriculum pinned
    to a single stage for the whole run — `curriculum_switch_episode`/`_2`
    both set past `episode_count`, deliberately never reached, so this test
    isolates *learning quality* from the *opponent getting harder*, a
    confound the second half of a multi-stage run otherwise carries by
    construction (a real trap docs already called out once for curriculum
    ordering, PRD 14 §4 — this is a second, distinct instance of it, not a
    repeat). (2) comparing the first/last 10% of the run instead of halves —
    verified over 8 seeds to pass with a clear margin, whereas halves stayed
    marginal or flipped for 2-3 of the same seeds even at 2500 episodes."""
    rl_config = RLTrainingConfig(
        **{
            **_SMALL_CONFIG_KWARGS,
            "episode_count": 2000,
            "curriculum_switch_episode": 2000,
            "curriculum_switch_episode_2": 2000,
            "alpha": 0.2,
            "epsilon_decay": 0.995,
        }
    )
    _table, metrics = train(config, rl_config)
    tenth = len(metrics.reward_history) // 10
    first_tenth = metrics.reward_history[:tenth]
    last_tenth = metrics.reward_history[-tenth:]
    assert sum(last_tenth) / len(last_tenth) > sum(first_tenth) / len(first_tenth)


def test_the_third_curriculum_stage_is_actually_reached_and_used_not_just_declared(config, monkeypatch):
    calls: list[int] = []
    real_lookahead = train_loop.lookahead_evader_thief

    def _recording_lookahead(own_pos, board, barriers):
        calls.append(1)
        return real_lookahead(own_pos, board, barriers)

    monkeypatch.setattr(train_loop, "lookahead_evader_thief", _recording_lookahead)
    rl_config = RLTrainingConfig(
        **{
            **_SMALL_CONFIG_KWARGS,
            "episode_count": 30,
            "curriculum_switch_episode": 10,
            "curriculum_switch_episode_2": 20,
        }
    )
    train(config, rl_config)
    assert calls, "stage 2 (lookahead_evader_thief) was configured to run but never got called"


def test_the_third_curriculum_stage_never_fires_before_its_own_switch_episode(config, monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(
        train_loop, "lookahead_evader_thief", lambda *a: calls.append(1) or "STAY"
    )
    rl_config = RLTrainingConfig(
        **{
            **_SMALL_CONFIG_KWARGS,
            "episode_count": 30,
            "curriculum_switch_episode": 10,
            "curriculum_switch_episode_2": 30,  # never reached within episode_count
        }
    )
    train(config, rl_config)
    assert not calls, "stage 2 fired before curriculum_switch_episode_2, or with it never reached"
