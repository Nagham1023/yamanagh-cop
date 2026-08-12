"""training/pipeline/stages.py: each stage runnable standalone, writes
exactly the artifact it claims, and reads only what the prior stage wrote."""

from __future__ import annotations

import dataclasses

import pytest

from training.config import RLTrainingConfig
from training.pipeline import artifacts, stages

_SMALL_RL_CONFIG_OVERRIDES = {"episode_count": 300, "curriculum_switch_episode": 150}


@pytest.fixture
def rl_config() -> RLTrainingConfig:
    return RLTrainingConfig.from_toml("config/rl_training.toml")


def _small_rl_config(rl_config: RLTrainingConfig) -> RLTrainingConfig:
    return dataclasses.replace(rl_config, **_SMALL_RL_CONFIG_OVERRIDES)


def test_run_train_writes_checkpoint_and_train_metrics(config, rl_config, tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    payload = stages.run_train(config, _small_rl_config(rl_config), "r1")
    assert artifacts.checkpoint_path("r1").exists()
    assert artifacts.stage_metrics_exist("r1", "train")
    assert payload["episode_count"] == 300
    assert artifacts.read_stage_metrics("r1", "train")["states_visited"] == payload["states_visited"]


def test_run_evaluate_reads_the_checkpoint_train_already_wrote(config, rl_config, tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    stages.run_train(config, _small_rl_config(rl_config), "r1")
    payload = stages.run_evaluate(config, "r1")
    assert artifacts.stage_metrics_exist("r1", "evaluate")
    assert 0.0 <= payload["rl_capture_rate"] <= 1.0
    assert 0.0 <= payload["baseline_capture_rate"] <= 1.0
    assert payload["win_rate_vs_baseline"] == payload["rl_capture_rate"]


def test_run_quantize_reads_the_checkpoint_and_writes_a_smaller_quantized_one(
    config, rl_config, tmp_path, monkeypatch
):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    stages.run_train(config, rl_config, "r1")  # full episode count -> a non-trivial table
    payload = stages.run_quantize("r1")
    assert artifacts.quantized_checkpoint_path("r1").exists()
    assert 0.0 <= payload["argmax_agreement_rate"] <= 1.0
    assert payload["size_after_bytes"] < payload["size_before_bytes"]


def test_run_benchmark_uses_the_quantized_checkpoint_when_it_exists(config, rl_config, tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    stages.run_train(config, _small_rl_config(rl_config), "r1")
    stages.run_quantize("r1")
    payload = stages.run_benchmark(config, rl_config, "r1")
    assert payload["sample_count"] > 0
    assert payload["p50_seconds"] <= payload["p95_seconds"] <= payload["p99_seconds"]
    assert payload["response_timeout_seconds"] == config.response_timeout_seconds


def test_run_benchmark_falls_back_to_the_unquantized_checkpoint_when_no_quantized_one_exists(
    config, rl_config, tmp_path, monkeypatch
):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    stages.run_train(config, _small_rl_config(rl_config), "r1")
    assert not artifacts.quantized_checkpoint_path("r1").exists()
    payload = stages.run_benchmark(config, rl_config, "r1")  # must not raise
    assert payload["sample_count"] > 0
