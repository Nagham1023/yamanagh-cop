"""rl_checkpoint: canonical JSON save/load, and loud failure on a corrupted file."""

from __future__ import annotations

import json

import pytest

from cop.reasoning.rl_checkpoint import load_checkpoint, save_checkpoint
from cop.reasoning.rl_checkpoint_quant import PerRowQuantizationParams, QuantizationParams

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


def test_a_quantized_checkpoint_dequantizes_transparently_on_load(tmp_path):
    path = tmp_path / "checkpoint.json"
    params = QuantizationParams(dtype="int8", scale=2.0, min_q=-10.0)
    quantized_values = {(0, 0, 0): {"N": 127, "E": -128}}  # N clearly best
    save_checkpoint(path, quantized_values, quantization=params)
    table = load_checkpoint(path)
    assert table.ranked_actions((0, 0, 0)) == ["N", "E"]


def test_a_real_pre_per_row_mode_quantized_checkpoint_still_loads_unchanged(tmp_path):
    """PRD 14 added a `"mode"` key inside `"quantization"` to distinguish
    per-row from per-table. A real file `save_checkpoint` produced before
    that key existed (the exact PRD-12/13 shape: `"quantization"` has
    `dtype`/`scale`/`min_q` and nothing else) must still load as per-table,
    not raise or silently misread as per-row — verified against a real,
    hand-constructed file matching that exact old shape, not re-asserted
    from `quantization_from_json`'s own docstring."""
    path = tmp_path / "checkpoint.json"
    payload = {
        "state_encoding_version": "v5",
        "quantization": {"dtype": "int8", "scale": 2.0, "min_q": -10.0},
        "q_values": [{"state": [0, 0, 0, 0, 0, 0, 0, 0], "values": {"N": 127, "E": -128}}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    table = load_checkpoint(path)
    assert table.ranked_actions((0, 0, 0, 0, 0, 0, 0, 0)) == ["N", "E"]


def test_a_per_row_quantized_checkpoint_dequantizes_each_state_with_its_own_params(tmp_path):
    path = tmp_path / "checkpoint.json"
    quantized_values = {
        (0, 0, 0, 0, 0, 0): {"N": 127, "E": -128},
        (1, 1, 0, 0, 0, 0): {"STAY": 0},
    }
    params = PerRowQuantizationParams(
        dtype="int8", rows={(0, 0, 0, 0, 0, 0): (2.0, -10.0), (1, 1, 0, 0, 0, 0): (0.5, 3.0)}
    )
    save_checkpoint(path, quantized_values, quantization=params)
    table = load_checkpoint(path)
    assert table.ranked_actions((0, 0, 0, 0, 0, 0)) == ["N", "E"]
    assert table.as_dict()[(1, 1, 0, 0, 0, 0)]["STAY"] == (0 + 128) * 0.5 + 3.0


def test_a_checkpoint_with_no_quantization_key_at_all_still_loads(tmp_path):
    """Simulates a file written before PRD 12 existed — `quantization` is
    entirely absent, not present-and-null. Tagged with the *current* encoding
    version, since "missing quantization key" and "old encoding version" are
    two independent concerns (see the v1/v2-specific tests below, which check
    the latter alone)."""
    path = tmp_path / "checkpoint.json"
    payload = {
        "state_encoding_version": "v5",
        "q_values": [{"state": [1, 2, 0, 3, 0, 2, 0, 0], "values": {"N": 4.5, "E": 1.0}}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    table = load_checkpoint(path)
    assert table.ranked_actions((1, 2, 0, 3, 0, 2, 0, 0)) == ["N", "E"]


def test_a_real_prd11_era_v1_checkpoint_now_fails_closed_not_silently(tmp_path):
    """The current version ("v5") has moved on four times since PRD 11's
    original "v1" (3-tuple). A genuine PRD-11-era "v1" file — the actual
    shape training produced before any sub-layer existed — must raise, not
    be silently misread. `RLCopBrain._load_or_none` is what turns this
    raise into a safe heuristic fallback (see test_rl_cop_brain.py's own
    counterpart test) — this test only proves the raise itself."""
    path = tmp_path / "checkpoint.json"
    payload = {
        "state_encoding_version": "v1",
        "q_values": [{"state": [1, 2, 0], "values": {"N": 4.5, "E": 1.0}}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        load_checkpoint(path)


def test_a_real_prd14_sub_layer_a_v2_checkpoint_now_fails_closed_not_silently(tmp_path):
    """A genuine "v2" file (sub-layer A's own 4-tuple shape, belief-
    confidence not yet entropy) must raise, the same fail-closed treatment
    "v1" already gets, not be silently misread as a 6-tuple with
    entropy-bucket semantics at index 3."""
    path = tmp_path / "checkpoint.json"
    payload = {
        "state_encoding_version": "v2",
        "q_values": [{"state": [1, 2, 0, 3], "values": {"N": 4.5, "E": 1.0}}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        load_checkpoint(path)


def test_a_real_prd14_sub_layer_b_v3_checkpoint_now_fails_closed_not_silently(tmp_path):
    """PRD 14 post-gate bumped the version to "v4" — a real "v3"
    file (sub-layer B's own 6-tuple shape, but index 3 still peak-
    probability semantics, not entropy) must now also raise. Same tuple
    *shape* as that version, different *meaning* at one position — exactly
    the silent-misread failure mode the version guard exists to catch, not
    just a shape mismatch."""
    path = tmp_path / "checkpoint.json"
    payload = {
        "state_encoding_version": "v3",
        "q_values": [{"state": [1, 2, 0, 3, 0, 2], "values": {"N": 4.5, "E": 1.0}}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        load_checkpoint(path)


def test_a_real_prd14_round2_v4_checkpoint_now_fails_closed_not_silently(tmp_path):
    """PRD 14 round-2 post-gate bumped the current version to "v5" — a real
    "v4" file (the correct OLD 6-tuple shape, no `dx2`/`dy2` at all) must
    now also raise rather than being silently misread as an 8-tuple with
    two trailing fields it never had. A real shape change this time, not
    just a semantic one like v3->v4."""
    path = tmp_path / "checkpoint.json"
    payload = {
        "state_encoding_version": "v4",
        "q_values": [{"state": [1, 2, 0, 3, 0, 2], "values": {"N": 4.5, "E": 1.0}}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        load_checkpoint(path)
