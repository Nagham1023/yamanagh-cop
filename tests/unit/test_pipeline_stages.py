"""training/pipeline/stages.py: each stage runnable standalone, writes
exactly the artifact it claims, and reads only what the prior stage wrote."""

from __future__ import annotations

import dataclasses
import subprocess

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


def test_run_train_writes_checkpoint_and_train_metrics(config, rl_config, tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    payload = stages.run_train(config, _small_rl_config(rl_config), "r1", _GAME_CONFIG_PATH)
    assert artifacts.checkpoint_path("r1").exists()
    assert artifacts.stage_metrics_exist("r1", "train")
    assert payload["episode_count"] == 300
    assert artifacts.read_stage_metrics("r1", "train")["states_visited"] == payload["states_visited"]


def test_run_train_writes_a_provenance_record_matching_the_real_repo(
    config, rl_config, tmp_path, monkeypatch
):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    stages.run_train(config, _small_rl_config(rl_config), "r1", _GAME_CONFIG_PATH)

    assert artifacts.stage_metrics_exist("r1", "provenance")
    provenance = artifacts.read_stage_metrics("r1", "provenance")

    real_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
    ).stdout.strip()
    assert provenance["git_commit_hash"] == real_commit
    assert provenance["hardware"]["llm_model"] == "none"
    assert provenance["game_config_path"] == _GAME_CONFIG_PATH
    # Round-trips the *actual* config passed in, not a hardcoded snapshot —
    # proven by asserting against the exact overrides this test itself applied.
    assert provenance["rl_training_config"]["episode_count"] == 300
    assert provenance["rl_training_config"]["curriculum_switch_episode"] == 150


def test_run_evaluate_reads_the_checkpoint_train_already_wrote(config, rl_config, tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    stages.run_train(config, _small_rl_config(rl_config), "r1", _GAME_CONFIG_PATH)
    payload = stages.run_evaluate(config, "r1")
    assert artifacts.stage_metrics_exist("r1", "evaluate")
    assert 0.0 <= payload["rl_capture_rate"] <= 1.0
    assert 0.0 <= payload["baseline_capture_rate"] <= 1.0
    assert payload["win_rate_vs_baseline"] == payload["rl_capture_rate"]


def test_run_quantize_reads_the_checkpoint_and_reports_high_argmax_agreement(
    config, rl_config, tmp_path, monkeypatch
):
    """PRD 14: per-row quantization trades some of PRD 12's per-table
    "always smaller" guarantee for much better decision fidelity — a real,
    measured trade-off (a real full-config run: 89.36% -> 100% argmax-
    agreement, ~218KB unquantized -> ~230KB quantized), not a regression.
    The size assertion below only guards against a *runaway* size blow-up
    (the kind a real duplicated-serialization bug produced once during
    development — 328KB, 50% over unquantized — before that bug was fixed),
    not "smaller than unquantized," which per-row no longer promises."""
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    stages.run_train(config, rl_config, "r1", _GAME_CONFIG_PATH)  # full episode count -> a non-trivial table
    payload = stages.run_quantize("r1")
    assert artifacts.quantized_checkpoint_path("r1").exists()
    assert payload["argmax_agreement_rate"] >= 0.99  # per-row's whole reason to exist
    assert payload["size_after_bytes"] < payload["size_before_bytes"] * 1.5


def test_run_benchmark_uses_the_quantized_checkpoint_when_it_exists(config, rl_config, tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    stages.run_train(config, _small_rl_config(rl_config), "r1", _GAME_CONFIG_PATH)
    stages.run_quantize("r1")
    payload = stages.run_benchmark(config, rl_config, "r1")
    assert payload["sample_count"] > 0
    assert payload["p50_seconds"] <= payload["p95_seconds"] <= payload["p99_seconds"]
    assert payload["response_timeout_seconds"] == config.response_timeout_seconds


def test_run_benchmark_falls_back_to_the_unquantized_checkpoint_when_no_quantized_one_exists(
    config, rl_config, tmp_path, monkeypatch
):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    stages.run_train(config, _small_rl_config(rl_config), "r1", _GAME_CONFIG_PATH)
    assert not artifacts.quantized_checkpoint_path("r1").exists()
    payload = stages.run_benchmark(config, rl_config, "r1")  # must not raise
    assert payload["sample_count"] > 0
