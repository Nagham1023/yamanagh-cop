"""PrivateConfig: loads [trash_talk] separately from GameConfig — never diffed
against the opponent's copy (PRD 4 Design Question 7)."""

from __future__ import annotations

import json

import pytest

from cop.shared.private_config import PrivateConfig

REPO_PRIVATE_CONFIG = "config/private/trash_talk_dev.json"


def test_loads_the_dev_private_config_from_disk():
    config = PrivateConfig.from_file(REPO_PRIVATE_CONFIG)
    assert config.provider == "template"
    assert config.every_n_steps == 1


def test_missing_provider_raises(tmp_path):
    path = tmp_path / "trash_talk.json"
    path.write_text(json.dumps({"every_n_steps": 1}), encoding="utf-8")

    with pytest.raises(KeyError):
        PrivateConfig.from_file(path)


def test_empty_provider_is_rejected():
    with pytest.raises(ValueError, match="provider"):
        PrivateConfig.from_dict({"provider": "", "every_n_steps": 1})


def test_non_positive_every_n_steps_is_rejected():
    with pytest.raises(ValueError, match="every_n_steps"):
        PrivateConfig.from_dict({"provider": "template", "every_n_steps": 0})


def test_this_loader_is_not_gameconfig_from_file():
    # Design Question 7's own point: a distinct loader, not a shape that
    # could accidentally be folded into the negotiated GameConfig object.
    from cop.shared.config import GameConfig

    assert PrivateConfig.from_file is not GameConfig.from_file
