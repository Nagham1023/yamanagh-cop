"""require_fresh_promotion_report_for_counted_game: the hard runtime safety
net auto-replace deployment needs in place of a config-edit-only gate."""

from __future__ import annotations

import hashlib
import json

import pytest

from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.rl_cop_brain import RLCopBrain
from cop.shared import promotion_guard


def test_uncounted_game_never_checks_anything_even_for_rl_cop_brain(tmp_path, monkeypatch):
    monkeypatch.setattr(promotion_guard, "PROMOTION_REPORT_PATH", tmp_path / "does_not_exist.json")
    brain = RLCopBrain(checkpoint_path=tmp_path / "missing.json")
    promotion_guard.require_fresh_promotion_report_for_counted_game(brain, counted=False)  # no raise


def test_counted_game_against_a_non_rl_brain_is_never_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(promotion_guard, "PROMOTION_REPORT_PATH", tmp_path / "does_not_exist.json")
    promotion_guard.require_fresh_promotion_report_for_counted_game(CopBrain(), counted=True)  # no raise


def test_counted_rl_cop_brain_with_no_promotion_report_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(promotion_guard, "PROMOTION_REPORT_PATH", tmp_path / "missing_report.json")
    brain = RLCopBrain(checkpoint_path=tmp_path / "missing_checkpoint.json")
    with pytest.raises(promotion_guard.StalePromotionError):
        promotion_guard.require_fresh_promotion_report_for_counted_game(brain, counted=True)


def test_counted_rl_cop_brain_with_a_report_but_missing_checkpoint_raises(tmp_path, monkeypatch):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({"checkpoint_sha256": "deadbeef"}), encoding="utf-8")
    monkeypatch.setattr(promotion_guard, "PROMOTION_REPORT_PATH", report_path)
    monkeypatch.setattr(promotion_guard, "DEFAULT_CHECKPOINT_PATH", str(tmp_path / "missing_checkpoint.json"))
    brain = RLCopBrain(checkpoint_path=tmp_path / "missing_checkpoint.json")
    with pytest.raises(promotion_guard.StalePromotionError):
        promotion_guard.require_fresh_promotion_report_for_counted_game(brain, counted=True)


def test_counted_rl_cop_brain_with_a_stale_hash_raises(tmp_path, monkeypatch):
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_text('{"state_encoding_version": "v1", "q_values": []}', encoding="utf-8")
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({"checkpoint_sha256": "not-the-real-hash"}), encoding="utf-8")

    monkeypatch.setattr(promotion_guard, "PROMOTION_REPORT_PATH", report_path)
    monkeypatch.setattr(promotion_guard, "DEFAULT_CHECKPOINT_PATH", str(checkpoint_path))
    brain = RLCopBrain(checkpoint_path=checkpoint_path)
    with pytest.raises(promotion_guard.StalePromotionError):
        promotion_guard.require_fresh_promotion_report_for_counted_game(brain, counted=True)


def test_counted_rl_cop_brain_with_a_matching_fresh_report_does_not_raise(tmp_path, monkeypatch):
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_text('{"state_encoding_version": "v1", "q_values": []}', encoding="utf-8")
    real_hash = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({"checkpoint_sha256": real_hash}), encoding="utf-8")

    monkeypatch.setattr(promotion_guard, "PROMOTION_REPORT_PATH", report_path)
    monkeypatch.setattr(promotion_guard, "DEFAULT_CHECKPOINT_PATH", str(checkpoint_path))
    brain = RLCopBrain(checkpoint_path=checkpoint_path)
    promotion_guard.require_fresh_promotion_report_for_counted_game(brain, counted=True)  # no raise
