"""GameConfig loading: acceptance from a real file, and rejection of an incomplete one."""

from __future__ import annotations

import json

import pytest

from cop.shared.config import GameConfig

REPO_CONFIG = "config/shared/config_dev_g01.json"


def test_loads_the_dev_config_from_disk():
    cfg = GameConfig.from_file(REPO_CONFIG)
    assert cfg.board_size == 7
    assert cfg.barrier_quota == 14
    assert cfg.thief_start == (3, 3)
    assert cfg.cop_start == (0, 0)


def test_missing_required_field_raises(tmp_path):
    incomplete = {"board_size": 7}  # everything else absent
    path = tmp_path / "config_incomplete.json"
    path.write_text(json.dumps(incomplete), encoding="utf-8")

    with pytest.raises(KeyError):
        GameConfig.from_file(path)


def _full_config(**overrides):
    """Base config dict identical to config_dev_g01.json, with fields overridable."""
    base = {
        "board_size": 7, "agent_count": 2, "origin": "top-left", "index_base": 0,
        "thief_start": [3, 3], "cop_start": [0, 0], "barrier_quota": 14,
        "step_ceiling": 35, "survival_threshold": 35,
        "score_capture_cop": 20, "score_capture_thief": 5,
        "score_survival_cop": 5, "score_survival_thief": 10, "score_draw": 2,
    }
    base.update(overrides)
    return base


def test_negative_board_size_is_rejected():
    # TODO1.md #4: a nonsensical value must fail at load time, not silently
    # propagate into Board/BarrierSet.
    with pytest.raises(ValueError, match="board_size"):
        GameConfig.from_dict(_full_config(board_size=-1))


def test_non_integer_barrier_quota_is_rejected():
    with pytest.raises(ValueError, match="barrier_quota"):
        GameConfig.from_dict(_full_config(barrier_quota="fourteen"))


def test_unsupported_origin_is_rejected():
    # TODO1.md #3: origin/index_base are NEGOTIABLE per Table 13, but
    # Position/Board only implement top-left/index-0 today — a config
    # negotiating anything else must fail loudly, not be silently misread.
    with pytest.raises(ValueError, match="origin"):
        GameConfig.from_dict(_full_config(origin="bottom-left"))


def test_unsupported_index_base_is_rejected():
    with pytest.raises(ValueError, match="index_base"):
        GameConfig.from_dict(_full_config(index_base=1))


def test_default_origin_and_index_base_are_accepted():
    config = GameConfig.from_dict(_full_config())
    assert config.origin == "top-left"
    assert config.index_base == 0
