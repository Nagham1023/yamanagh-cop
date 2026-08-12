"""training/pipeline/artifacts.py: per-run structured I/O."""

from __future__ import annotations

from training.pipeline import artifacts


def test_run_dir_creates_the_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    path = artifacts.run_dir("myrun")
    assert path.is_dir()
    assert path == tmp_path / "myrun"


def test_checkpoint_path_and_quantized_checkpoint_path_are_distinct(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    assert artifacts.checkpoint_path("r") != artifacts.quantized_checkpoint_path("r")
    assert artifacts.checkpoint_path("r").name == "checkpoint.json"
    assert artifacts.quantized_checkpoint_path("r").name == "checkpoint_quantized.json"


def test_write_then_read_stage_metrics_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    artifacts.write_stage_metrics("r1", "train", {"episode_count": 100, "final_epsilon": 0.05})
    loaded = artifacts.read_stage_metrics("r1", "train")
    assert loaded == {"episode_count": 100, "final_epsilon": 0.05}


def test_stage_metrics_exist_is_false_before_write_and_true_after(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    assert artifacts.stage_metrics_exist("r1", "evaluate") is False
    artifacts.write_stage_metrics("r1", "evaluate", {"win_rate_vs_baseline": 1.0})
    assert artifacts.stage_metrics_exist("r1", "evaluate") is True


def test_write_stage_metrics_writes_canonical_json(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RUNS_ROOT", tmp_path)
    path = artifacts.write_stage_metrics("r1", "train", {"b": 2, "a": 1})
    raw = path.read_text(encoding="utf-8")
    assert ", " not in raw
    assert raw.index('"a"') < raw.index('"b"')  # sort_keys
