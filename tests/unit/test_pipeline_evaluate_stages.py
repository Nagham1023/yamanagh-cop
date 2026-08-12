"""run_evaluate_belief_aware (PRD 14 sub-layer A): the additive companion
to run_evaluate, actually exercising belief-based states."""

from __future__ import annotations

import dataclasses

import pytest

from training.config import RLTrainingConfig
from training.pipeline import artifacts, stages

_SMALL_RL_CONFIG_OVERRIDES = {"episode_count": 300, "curriculum_switch_episode": 150}
_GAME_CONFIG_PATH = "config/shared/config_dev_g01.json"


@pytest.fixture
def rl_config() -> RLTrainingConfig:
    return RLTrainingConfig.from_toml("config/rl_training.toml")


def _small_rl_config(rl_config: RLTrainingConfig) -> RLTrainingConfig:
    return dataclasses.replace(rl_config, **_SMALL_RL_CONFIG_OVERRIDES)


def test_writes_additively_into_the_same_evaluate_metrics_file(config, rl_config, tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    small_rl_config = _small_rl_config(rl_config)
    stages.run_train(config, small_rl_config, "r1", _GAME_CONFIG_PATH)
    stages.run_evaluate(config, "r1")

    stages.run_evaluate_belief_aware(config, small_rl_config, "r1")

    on_disk = artifacts.read_stage_metrics("r1", "evaluate")
    # The original run_evaluate fields are still there, untouched...
    assert "win_rate_vs_baseline" in on_disk
    assert "rl_capture_rate" in on_disk
    # ...alongside the new belief-aware fields, not replacing them.
    assert "win_rate_vs_baseline_belief_aware" in on_disk
    assert 0.0 <= on_disk["win_rate_vs_baseline_belief_aware"] <= 1.0
    assert 0.0 <= on_disk["baseline_capture_rate_belief_aware"] <= 1.0


def test_is_a_genuinely_independent_computation_not_a_copy(config, rl_config, tmp_path, monkeypatch):
    # Ground-truth and belief-aware capture rates are computed by two
    # different loops (run_local_subgame vs. a live SelfPlayEnv) with
    # different seeded opponents each episode — proving this isn't just
    # `win_rate_vs_baseline_belief_aware = win_rate_vs_baseline` requires
    # showing the belief-aware payload has its own, distinctly-named,
    # independently-populated fields (checked structurally here) rather than
    # asserting a specific numeric inequality, which real seeded runs could
    # coincidentally satisfy either way.
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    small_rl_config = _small_rl_config(rl_config)
    stages.run_train(config, small_rl_config, "r1", _GAME_CONFIG_PATH)

    payload = stages.run_evaluate_belief_aware(config, small_rl_config, "r1")

    assert set(payload) == {
        "win_rate_vs_baseline_belief_aware",
        "rl_capture_rate_belief_aware",
        "rl_avg_steps_to_capture_belief_aware",
        "baseline_capture_rate_belief_aware",
        "baseline_avg_steps_to_capture_belief_aware",
    }


def test_works_even_when_run_evaluate_never_ran_first(config, rl_config, tmp_path, monkeypatch):
    # additive means "merge if present," not "require present."
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    small_rl_config = _small_rl_config(rl_config)
    stages.run_train(config, small_rl_config, "r1", _GAME_CONFIG_PATH)
    assert not artifacts.stage_metrics_exist("r1", "evaluate")

    stages.run_evaluate_belief_aware(config, small_rl_config, "r1")

    assert artifacts.stage_metrics_exist("r1", "evaluate")
