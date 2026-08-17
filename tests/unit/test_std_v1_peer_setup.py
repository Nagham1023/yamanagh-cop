"""std_v1/peer_setup.py tests."""

from __future__ import annotations

import json

from cop.reasoning.cop_brain import CopBrain
from cop.shared.private_config import PrivateConfig
from cop.std_v1.peer_setup import (
    build_std_v1_game_config,
    build_turn_handler_factory,
    write_std_v1_result,
)
from cop.std_v1.terms import load_terms

TERMS = load_terms()


def test_build_std_v1_game_config_overrides_interop_fields(config):
    interop_config = build_std_v1_game_config(config, TERMS)
    assert interop_config.board_size == TERMS["board_size"]
    assert interop_config.thief_start == tuple(TERMS["thief_start"])
    assert interop_config.cop_start == tuple(TERMS["cop_start"])
    assert interop_config.barrier_quota == TERMS["barriers_max"]
    assert interop_config.step_ceiling == TERMS["max_steps"]
    assert interop_config.arena == TERMS["setting"]
    assert interop_config.hint_word_limit == TERMS["hint_max_words"]
    assert interop_config.scent_field_size == TERMS["smell_grid_size"]


def test_build_std_v1_game_config_keeps_native_only_fields_from_base(config):
    interop_config = build_std_v1_game_config(config, TERMS)
    assert interop_config.score_capture_cop == config.score_capture_cop
    assert interop_config.watchdog_threshold_seconds == config.watchdog_threshold_seconds


def _private_config(**overrides) -> PrivateConfig:
    base = {
        "provider": "template", "every_n_steps": 1, "opponent_url": "http://x", "my_port": 8801,
        "turn_timeout_seconds": 30.0, "initiate_step0": False, "step0_wait_seconds": 300.0,
        "scent_map_retry_attempts": 3, "scent_map_retry_delay_seconds": 1.0, "post_match_grace_seconds": 60.0,
        "group_name": "dev-team", "group_id": "dev-team", "sub_game_number": 1, "members": ("dev-1",),
        "repos": {}, "model": "claude-sonnet-5", "step_deadline_seconds": 30.0, "email_recipient": "x@y.com",
        "email_mode": "draft",
    }
    base.update(overrides)
    return PrivateConfig(**base)


def test_build_turn_handler_factory_builds_a_fresh_handler_at_cop_start(config):
    interop_config = build_std_v1_game_config(config, TERMS)
    factory = build_turn_handler_factory(interop_config, _private_config(), CopBrain)
    handler = factory()
    assert (handler.state.own_pos.col, handler.state.own_pos.row) == tuple(TERMS["cop_start"])


def test_build_turn_handler_factory_resets_state_on_each_call(config):
    interop_config = build_std_v1_game_config(config, TERMS)
    factory = build_turn_handler_factory(interop_config, _private_config(), CopBrain)
    first = factory()
    first.play_turn({}, "")
    second = factory()
    assert (second.state.own_pos.col, second.state.own_pos.row) == tuple(TERMS["cop_start"])
    assert second.state.steps_taken == 0


def test_write_std_v1_result_writes_the_result_json(tmp_path):
    result = {"game_id": "dev-team-vs-thief-team", "agreed": True}
    out_path = write_std_v1_result(result, tmp_path)
    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8")) == result
