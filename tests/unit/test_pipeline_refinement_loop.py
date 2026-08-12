"""run_train_eval_cycle: hard iteration cap, explicit coverage criterion,
and wall-clock budget — each independently proven, not just "usually
converges" (PLAN.md §6's non-negotiable requirement)."""

from __future__ import annotations

import dataclasses

import pytest

from training.config import RLTrainingConfig
from training.pipeline import artifacts
from training.pipeline.refinement_loop import run_train_eval_cycle


@pytest.fixture
def rl_config() -> RLTrainingConfig:
    return RLTrainingConfig.from_toml("config/rl_training.toml")


def test_a_trivially_reachable_target_converges_on_round_one(config, rl_config, tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    easy = dataclasses.replace(
        rl_config, episode_count=300, max_refinement_rounds=3, win_rate_target=0.0,
        wall_clock_budget_seconds=60.0,
    )
    result = run_train_eval_cycle(config, easy, "easy")
    assert result.converged is True
    assert result.rounds_run == 1
    assert result.best_run_id == "easy_round1"


def test_an_unreachable_target_stops_at_the_hard_cap_not_forever(config, rl_config, tmp_path, monkeypatch):
    """Proves the cap actually stops the loop — a fixture that can never
    meet the criterion, not just a happy-path run that coincidentally converges."""
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    impossible = dataclasses.replace(
        rl_config, episode_count=200, max_refinement_rounds=2, win_rate_target=2.0,
        wall_clock_budget_seconds=60.0,
    )
    result = run_train_eval_cycle(config, impossible, "never")
    assert result.converged is False
    assert result.rounds_run == 2  # exactly the cap, not more
    assert len(result.refinement_log) == 2


def test_each_failing_round_doubles_episode_count_by_a_fixed_rule(config, rl_config, tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    impossible = dataclasses.replace(
        rl_config, episode_count=100, max_refinement_rounds=3, win_rate_target=2.0,
        wall_clock_budget_seconds=60.0,
    )
    result = run_train_eval_cycle(config, impossible, "doubling")
    episode_counts = [entry["episode_count"] for entry in result.refinement_log]
    assert episode_counts == [100, 200, 400]


def test_a_zero_wall_clock_budget_stops_before_the_first_round_even_starts(
    config, rl_config, tmp_path, monkeypatch
):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    zero_budget = dataclasses.replace(
        rl_config, max_refinement_rounds=3, win_rate_target=0.0, wall_clock_budget_seconds=0.0
    )
    result = run_train_eval_cycle(config, zero_budget, "no_time")
    assert result.rounds_run == 0
    assert result.converged is False
    assert result.best_run_id is None


def test_the_result_is_persisted_as_an_artifact_readers_can_find_without_rerunning(
    config, rl_config, tmp_path, monkeypatch
):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    easy = dataclasses.replace(
        rl_config, episode_count=300, max_refinement_rounds=1, win_rate_target=0.0,
        wall_clock_budget_seconds=60.0,
    )
    result = run_train_eval_cycle(config, easy, "persisted")
    on_disk = artifacts.read_stage_metrics("persisted", "refinement")
    assert on_disk["best_run_id"] == result.best_run_id
    assert on_disk["converged"] == result.converged
    assert len(on_disk["refinement_log"]) == len(result.refinement_log)


def test_when_the_cap_is_exhausted_the_best_round_is_returned_not_the_last_blindly(
    config, rl_config, tmp_path, monkeypatch
):
    """Distinct from 'last' whenever win-rate isn't monotonically improving
    round to round — this repo's own stated principle, checked, not assumed."""
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    impossible = dataclasses.replace(
        rl_config, episode_count=150, max_refinement_rounds=3, win_rate_target=2.0,
        wall_clock_budget_seconds=60.0,
    )
    result = run_train_eval_cycle(config, impossible, "best_not_last")
    best_win_rate = next(
        e["win_rate"] for e in result.refinement_log if f"best_not_last_round{e['round']}" == result.best_run_id
    )
    assert best_win_rate == max(e["win_rate"] for e in result.refinement_log)
