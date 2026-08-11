"""rl_checkpoint: canonical JSON save/load, and loud failure on a corrupted file."""

from __future__ import annotations

import json

import pytest

from cop.reasoning.rl_checkpoint import load_checkpoint, save_checkpoint

_Q_VALUES = {(1, 2, 0): {"N": 4.5, "E": 1.0}, (-1, 0, 3): {"STAY": 0.2}}


def test_save_then_load_round_trips_ranked_actions(tmp_path):
    path = tmp_path / "checkpoint.json"
    save_checkpoint(path, _Q_VALUES)
    table = load_checkpoint(path)
    assert table.ranked_actions((1, 2, 0)) == ["N", "E"]
    assert table.ranked_actions((-1, 0, 3)) == ["STAY"]


def test_unvisited_state_returns_none_not_an_empty_list(tmp_path):
    path = tmp_path / "checkpoint.json"
    save_checkpoint(path, _Q_VALUES)
    table = load_checkpoint(path)
    assert table.ranked_actions((9, 9, 9)) is None


def test_save_writes_canonical_json(tmp_path):
    path = tmp_path / "checkpoint.json"
    save_checkpoint(path, _Q_VALUES)
    raw = path.read_text(encoding="utf-8")
    # sort_keys + compact separators, matching this repo's own commit-payload
    # canonicalization habit (not cryptographic here, just reproducibility)
    assert ", " not in raw
    assert ": " not in raw


def test_missing_file_raises_file_not_found_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_checkpoint(tmp_path / "does_not_exist.json")


def test_not_json_raises_value_error(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_text("not json at all {{{", encoding="utf-8")
    with pytest.raises(ValueError):
        load_checkpoint(path)


def test_missing_required_keys_raises_value_error(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps({"unrelated": True}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_checkpoint(path)


def test_unrecognized_encoding_version_raises_value_error(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps({"state_encoding_version": "v999", "q_values": []}), encoding="utf-8"
    )
    with pytest.raises(ValueError):
        load_checkpoint(path)
