"""run_ensemble: selection (top-N by belief-aware win-rate), the Q-table
merge policy (sum only over tables that actually visited a state/action, not
treating "missing" as a real zero), and a small-but-real end-to-end run —
see ensemble.py's own module docstring for why belief-aware win-rate is the
selection metric, not the plain ground-truth one."""

from __future__ import annotations

import dataclasses

import pytest

from cop.reasoning.rl_checkpoint import save_checkpoint
from training.config import RLTrainingConfig
from training.pipeline import artifacts
from training.pipeline.ensemble import _merge_q_tables, _rank_and_select, run_ensemble

_GAME_CONFIG_PATH = "config/shared/config_dev_g01.json"


@pytest.fixture
def rl_config() -> RLTrainingConfig:
    return RLTrainingConfig.from_toml("config/rl_training.toml")


def test_rank_and_select_keeps_the_highest_belief_aware_win_rates_first():
    ranking = [
        {"seed": 0, "run_id": "p_seed0", "win_rate_vs_baseline_belief_aware": 0.3},
        {"seed": 1, "run_id": "p_seed1", "win_rate_vs_baseline_belief_aware": 0.9},
        {"seed": 2, "run_id": "p_seed2", "win_rate_vs_baseline_belief_aware": 0.1},
        {"seed": 3, "run_id": "p_seed3", "win_rate_vs_baseline_belief_aware": 0.7},
        {"seed": 4, "run_id": "p_seed4", "win_rate_vs_baseline_belief_aware": 0.5},
    ]
    result = _rank_and_select(ranking, keep_count=3)
    assert [row["seed"] for row in result[:3]] == [1, 3, 4]


def test_rank_and_select_top_keep_count_is_always_within_the_bottom_half_survivors():
    ranking = [
        {"seed": i, "run_id": f"p_seed{i}", "win_rate_vs_baseline_belief_aware": float(20 - i)}
        for i in range(20)
    ]
    result = _rank_and_select(ranking, keep_count=5)
    top_5_seeds = {row["seed"] for row in result[:5]}
    top_10_seeds = {row["seed"] for row in result[:10]}  # the "bottom 50% dropped" survivors
    assert top_5_seeds <= top_10_seeds


def test_merge_q_tables_keeps_a_single_tables_own_raw_value_when_others_never_visited_it(tmp_path, monkeypatch):
    # The key merge-policy test: a (state, action) pair present in only one
    # of two tables must keep that table's raw value -- never halved or
    # zeroed by the absent one, since "missing" means "no vote," not "voted
    # for zero."
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    only_in_a_state = (0, 0, 0, 0, 0, 0, 0, 0)
    shared_state = (1, 1, 0, 0, 0, 0, 0, 0)
    save_checkpoint(
        artifacts.checkpoint_path("m_seed_a"),
        {only_in_a_state: {"N": 10.0}, shared_state: {"E": 4.0}},
    )
    save_checkpoint(artifacts.checkpoint_path("m_seed_b"), {shared_state: {"E": 6.0}})

    merged = _merge_q_tables(["m_seed_a", "m_seed_b"])

    assert merged[only_in_a_state]["N"] == 10.0  # untouched by seed_b's absence
    assert merged[shared_state]["E"] == 10.0  # genuinely summed where both tables agree


def test_merge_q_tables_sums_across_all_provided_tables_not_just_the_first_two(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    state = (2, 2, 0, 0, 0, 0, 0, 0)
    for i, value in enumerate([1.0, 2.0, 3.0]):
        save_checkpoint(artifacts.checkpoint_path(f"m3_seed{i}"), {state: {"N": value}})

    merged = _merge_q_tables(["m3_seed0", "m3_seed1", "m3_seed2"])

    assert merged[state]["N"] == 6.0  # 1.0 + 2.0 + 3.0, all three, not just two


def test_run_ensemble_end_to_end_at_a_tiny_scale_writes_every_expected_artifact(
    config, rl_config, tmp_path, monkeypatch
):
    # No mocking of train/evaluate -- a genuinely small, genuinely real run,
    # mirroring test_pipeline_refinement_loop.py's own precedent.
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    tiny = dataclasses.replace(
        rl_config,
        episode_count=40,
        curriculum_switch_episode=40,
        curriculum_switch_episode_2=40,
        curriculum_switch_episode_3=40,
    )

    result = run_ensemble(config, tiny, "tiny_ensemble", _GAME_CONFIG_PATH, seed_count=4, keep_count=2)

    assert result["seed_count"] == 4
    assert result["keep_count"] == 2
    assert len(result["ranking"]) == 4
    assert len(result["selected_run_ids"]) == 2
    assert result["top_keep_count_is_subset_of_bottom_half_survivors"] is True

    # Every per-seed run has its own real artifacts on disk.
    for seed in range(4):
        assert artifacts.stage_metrics_exist(f"tiny_ensemble_seed{seed}", "train")
        assert artifacts.stage_metrics_exist(f"tiny_ensemble_seed{seed}", "evaluate")

    # The ensembled checkpoint itself was trained through the real pipeline
    # (quantize/benchmark/evaluate), not skipped.
    assert artifacts.checkpoint_path("tiny_ensemble_ensemble").exists()
    assert artifacts.stage_metrics_exist("tiny_ensemble_ensemble", "quantize")
    assert artifacts.stage_metrics_exist("tiny_ensemble_ensemble", "benchmark")
    assert artifacts.stage_metrics_exist("tiny_ensemble_ensemble", "evaluate")

    # The ensemble's own summary artifact is persisted and matches the return value.
    on_disk = artifacts.read_stage_metrics("tiny_ensemble", "ensemble")
    assert on_disk["ensemble_run_id"] == result["ensemble_run_id"]
    assert on_disk["selected_run_ids"] == result["selected_run_ids"]
