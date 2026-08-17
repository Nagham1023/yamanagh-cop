"""PrivateConfig: loads config/game.toml separately from GameConfig — never
diffed against the opponent's copy (PRD 4 Design Question 7). TOML, six
sections, per Appendix B p.130-132 (todoFullFix.md §B)."""

from __future__ import annotations

import tomllib

import pytest

from cop.shared.private_config import PrivateConfig

REPO_PRIVATE_CONFIG = "config/game.toml"


def _full_private(**section_overrides):
    """Base nested dict matching config/game.toml's shape, with per-section
    overrides: `_full_private(network={"opponent_url": "..."})`."""
    base = {
        "version": "1.10",
        "game": {
            "group_name": "dev-team", "group_id": "dev-team", "sub_game_number": 1,
            "members": ["dev-1"],
            "repos": {"cop": "https://github.com/dev-team/cop-repo", "thief": "https://github.com/dev-team/thief-repo"},
        },
        "network": {
            "my_port": 8801, "opponent_url": "http://127.0.0.1:8802/mcp", "turn_timeout_seconds": 180,
        },
        "trash_talk": {"provider": "template", "every_n_steps": 1},
        "llm": {"model": "claude-sonnet-5", "step_deadline_seconds": 30},
        "email": {"recipient": "rmisegal+uoh26finalgame@gmail.com", "mode": "draft"},
    }
    for key, value in section_overrides.items():
        if isinstance(base.get(key), dict) and isinstance(value, dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def test_loads_the_dev_private_config_from_disk():
    config = PrivateConfig.from_file(REPO_PRIVATE_CONFIG)
    assert config.provider == "template"
    assert config.every_n_steps == 1
    # real-match wiring (PRD 5/10's tunnel), not the old localhost
    # placeholder — flips whenever the two teams agree a new opponent URL,
    # same "real file, real regression check" discipline as police_class
    # below. Switched to a Cloudflare Quick Tunnel URL once ngrok's
    # free-tier connection-rate cap was diagnosed as the round-26/27
    # match failure's real cause — the URL itself is ephemeral (a fresh
    # one every relaunch), so this will flip again on the next real match.
    assert config.opponent_url == "https://viewer-bangkok-notebooks-promotion.trycloudflare.com/mcp"
    assert config.my_port == 8801
    assert config.turn_timeout_seconds == 180.0
    assert config.group_name == "dev-team"
    assert config.members == ("dev-1",)
    assert config.repos["cop"] == "https://github.com/Nagham1023/yamanagh-cop"
    assert config.model == "claude-sonnet-5"
    assert config.email_recipient == "rmisegal+uoh26finalgame@gmail.com"
    assert config.thief_class is None
    # PRD 14 round-2 post-gate: RLCopBrain was promoted 2026-08-13 (see
    # training/promoted/promotion_report.json) — the real config/game.toml
    # now sets police_class, and this real-file regression check flips to
    # match, the same way test_cli_peer_build.py's own zero-regression
    # proof already did.
    assert config.police_class == "cop.reasoning.rl_cop_brain:RLCopBrain"
    assert config.initiate_step0 is False
    assert config.step0_wait_seconds == 300.0
    assert config.scent_map_retry_attempts == 3
    assert config.scent_map_retry_delay_seconds == 1.0
    assert config.post_match_grace_seconds == 60.0


def test_it_is_really_toml_not_json(tmp_path):
    # A JSON file handed to this loader must fail — proves the migration
    # away from JSON is real, not just a renamed extension.
    path = tmp_path / "game.toml"
    path.write_text('{"provider": "template", "every_n_steps": 1}', encoding="utf-8")

    with pytest.raises(tomllib.TOMLDecodeError):
        PrivateConfig.from_file(path)


def test_missing_section_raises(tmp_path):
    path = tmp_path / "game.toml"
    path.write_text('version = "1.10"\n[game]\ngroup_name = "x"\n', encoding="utf-8")

    with pytest.raises(KeyError):
        PrivateConfig.from_file(path)


def test_empty_provider_is_rejected():
    with pytest.raises(ValueError, match="provider"):
        PrivateConfig.from_dict(_full_private(trash_talk={"provider": ""}))


def test_non_positive_every_n_steps_is_rejected():
    with pytest.raises(ValueError, match="every_n_steps"):
        PrivateConfig.from_dict(_full_private(trash_talk={"every_n_steps": 0}))


def test_strategy_section_is_optional_and_defaults_to_none():
    # [strategy] is commented out in the book's own example — not built yet
    # (PRD 4's "Explicitly out of scope") — must not raise when absent.
    config = PrivateConfig.from_dict(_full_private())
    assert config.thief_class is None
    assert config.police_class is None


def test_strategy_section_is_read_when_present():
    config = PrivateConfig.from_dict(
        _full_private(strategy={"police_class": "my_team.strategy:MyPoliceBrain"})
    )
    assert config.police_class == "my_team.strategy:MyPoliceBrain"


def test_opponent_url_round_trips_from_network_section():
    config = PrivateConfig.from_dict(
        _full_private(network={"opponent_url": "http://203.0.113.5:9000/mcp"})
    )
    assert config.opponent_url == "http://203.0.113.5:9000/mcp"


def test_initiate_step0_and_step0_wait_seconds_default_safely_when_absent():
    # Matches [strategy]'s own "absent must not raise" discipline — an
    # older config file predating PRD 10 must keep loading unchanged.
    config = PrivateConfig.from_dict(_full_private())
    assert config.initiate_step0 is False
    assert config.step0_wait_seconds == 300.0


def test_initiate_step0_and_step0_wait_seconds_round_trip_when_present():
    config = PrivateConfig.from_dict(
        _full_private(network={"initiate_step0": True, "step0_wait_seconds": 60})
    )
    assert config.initiate_step0 is True
    assert config.step0_wait_seconds == 60.0


def test_scent_map_retry_settings_default_safely_when_absent():
    # Older config file predating this pair must keep loading unchanged,
    # same discipline as initiate_step0/step0_wait_seconds above.
    config = PrivateConfig.from_dict(_full_private())
    assert config.scent_map_retry_attempts == 3
    assert config.scent_map_retry_delay_seconds == 1.0


def test_scent_map_retry_settings_round_trip_when_present():
    config = PrivateConfig.from_dict(
        _full_private(network={"scent_map_retry_attempts": 4, "scent_map_retry_delay_seconds": 1.5})
    )
    assert config.scent_map_retry_attempts == 4
    assert config.scent_map_retry_delay_seconds == 1.5


def test_post_match_grace_seconds_defaults_safely_when_absent():
    config = PrivateConfig.from_dict(_full_private())
    assert config.post_match_grace_seconds == 60.0


def test_post_match_grace_seconds_round_trips_when_present():
    config = PrivateConfig.from_dict(_full_private(network={"post_match_grace_seconds": 15}))
    assert config.post_match_grace_seconds == 15.0


def test_opponent_protocol_defaults_to_native_when_absent():
    config = PrivateConfig.from_dict(_full_private())
    assert config.opponent_protocol == "native"
    assert config.opponent_group_id is None


def test_opponent_protocol_round_trips_when_present():
    config = PrivateConfig.from_dict(
        _full_private(network={"opponent_protocol": "std_v1", "opponent_group_id": "thief-team"})
    )
    assert config.opponent_protocol == "std_v1"
    assert config.opponent_group_id == "thief-team"


def test_this_loader_is_not_gameconfig_from_file():
    # Design Question 7's own point: a distinct loader, not a shape that
    # could accidentally be folded into the negotiated GameConfig object.
    from cop.shared.config import GameConfig

    assert PrivateConfig.from_file is not GameConfig.from_file
