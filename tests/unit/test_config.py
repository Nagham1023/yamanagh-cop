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
    assert cfg.response_timeout_seconds == 90.0
    assert cfg.watchdog_threshold_seconds == 120.0
    assert cfg.arena == "New York"
    assert cfg.hint_word_limit == 15
    assert cfg.scent_source_strength == 0.9
    assert cfg.scent_decay_rate == 0.10
    assert cfg.scent_field_size == 5


def test_missing_required_field_raises(tmp_path):
    incomplete = {"schema_version": "1.2", "agreed_between": ["a", "b"]}  # no board_and_agents etc.
    path = tmp_path / "config_incomplete.json"
    path.write_text(json.dumps(incomplete), encoding="utf-8")

    with pytest.raises(KeyError):
        GameConfig.from_file(path)


def test_old_flat_shape_fails_loudly_not_silently(tmp_path):
    # todoFullFix.md §A2: a config migration mistake (someone still hands us
    # the pre-correction flat shape) must fail loudly, not silently default
    # or partially load — proves the nested-schema migration doesn't quietly
    # tolerate the old shape it's supposed to have replaced.
    flat = {"board_size": 7, "agent_count": 2, "origin": "top-left", "index_base": 0}
    path = tmp_path / "config_flat.json"
    path.write_text(json.dumps(flat), encoding="utf-8")

    with pytest.raises(KeyError, match="board_and_agents"):
        GameConfig.from_file(path)


def _full_config(**overrides):
    """Base nested config dict, Appendix B's shape. Per-group overrides merge
    into that group: `_full_config(board_and_agents={"grid_size": -1})`. A
    top-level override (e.g. `schema_version=...`) replaces directly."""
    base = {
        "schema_version": "1.2",
        "agreed_between": ["group-a", "group-b"],
        "board_and_agents": {
            "grid_size": 7, "num_agents": 2, "thief_start": [3, 3], "cop_start": [0, 0],
            "axis_origin_corner": "top-left", "axis_start_index": 0,
        },
        "world": {"map_area": "New York", "hint_max_words": 15},
        "movement_and_barriers": {
            "move_set": ["N", "S", "E", "W", "STAY"],
            "max_barriers": 14, "max_moves": 35, "survival_threshold": 35,
        },
        "scoring": {
            "capture_cop": 20, "capture_thief": 5,
            "survival_cop": 5, "survival_thief": 10, "tie_score": 2, "technical_loss": 0,
        },
        "pheromones": {"pheromone_center_intensity": 0.9, "pheromone_decay": 0.10, "pheromone_grid_size": 5},
        "network_and_league": {
            "response_timeout_sec": 30, "watchdog_timeout_sec": 60, "token_budget_per_series": 200000,
        },
        "rate_limiter_gatekeeper": {
            "requests_per_minute": 30, "concurrent_requests": 2,
            "retry_backoff_sec": 5, "max_retries": 3, "queue_depth": 100,
        },
    }
    for key, value in overrides.items():
        if isinstance(base.get(key), dict) and isinstance(value, dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def test_book_appendix_b_literal_example_round_trips_exactly():
    # todoFullFix.md §A2: Appendix B's own literal p.129 example (the exact
    # JSON printed in the book, not a paraphrase), round-tripped through
    # from_dict() — every value must land on the matching GameConfig field.
    book_example = {
        "schema_version": "1.2",
        "agreed_between": ["group-a", "group-b"],
        "board_and_agents": {
            "grid_size": 7, "num_agents": 2, "thief_start": [3, 3], "cop_start": [0, 0],
            "axis_origin_corner": "top-left", "axis_start_index": 0,
        },
        "world": {"map_area": "New York", "hint_max_words": 15},
        "movement_and_barriers": {
            "move_set": ["N", "S", "E", "W", "STAY"],
            "max_barriers": 14, "max_moves": 35, "survival_threshold": 35,
        },
        "scoring": {
            "capture_cop": 20, "capture_thief": 5,
            "survival_cop": 5, "survival_thief": 10, "tie_score": 2, "technical_loss": 0,
        },
        "pheromones": {"pheromone_center_intensity": 0.9, "pheromone_decay": 0.10, "pheromone_grid_size": 5},
        "network_and_league": {
            "response_timeout_sec": 30, "watchdog_timeout_sec": 60,
            "num_games": 1, "diversity_reward": 10, "min_games_to_pass": 2,
            "max_games_per_team": 10, "token_budget_per_series": 200000,
        },
        "rate_limiter_gatekeeper": {
            "requests_per_minute": 30, "concurrent_requests": 2,
            "retry_backoff_sec": 5, "max_retries": 3, "queue_depth": 100,
        },
    }

    config = GameConfig.from_dict(book_example)

    assert config.board_size == 7
    assert config.agent_count == 2
    assert config.thief_start == (3, 3)
    assert config.cop_start == (0, 0)
    assert config.origin == "top-left"
    assert config.index_base == 0
    assert config.arena == "New York"
    assert config.hint_word_limit == 15
    assert config.barrier_quota == 14
    assert config.step_ceiling == 35
    assert config.survival_threshold == 35
    assert config.score_capture_cop == 20
    assert config.score_capture_thief == 5
    assert config.score_survival_cop == 5
    assert config.score_survival_thief == 10
    assert config.score_draw == 2
    assert config.scent_source_strength == 0.9
    assert config.scent_decay_rate == 0.10
    assert config.scent_field_size == 5
    assert config.response_timeout_seconds == 30.0
    assert config.watchdog_threshold_seconds == 60.0
    assert config.schema_version == "1.2"
    assert config.agreed_between == ("group-a", "group-b")


def test_negative_board_size_is_rejected():
    # TODO1.md #4: a nonsensical value must fail at load time, not silently
    # propagate into Board/BarrierSet.
    with pytest.raises(ValueError, match="grid_size"):
        GameConfig.from_dict(_full_config(board_and_agents={"grid_size": -1}))


def test_non_positive_num_agents_is_rejected():
    # rule-auditor finding on §A: num_agents was read raw, unlike every
    # other field — proves it's now validated too.
    with pytest.raises(ValueError, match="num_agents"):
        GameConfig.from_dict(_full_config(board_and_agents={"num_agents": 0}))


def test_non_integer_barrier_quota_is_rejected():
    with pytest.raises(ValueError, match="max_barriers"):
        GameConfig.from_dict(_full_config(movement_and_barriers={"max_barriers": "fourteen"}))


def test_unsupported_origin_is_rejected():
    # TODO1.md #3: origin/index_base are NEGOTIABLE per Table 13, but
    # Position/Board only implement top-left/index-0 today — a config
    # negotiating anything else must fail loudly, not be silently misread.
    with pytest.raises(ValueError, match="origin"):
        GameConfig.from_dict(_full_config(board_and_agents={"axis_origin_corner": "bottom-left"}))


def test_unsupported_index_base_is_rejected():
    with pytest.raises(ValueError, match="index_base"):
        GameConfig.from_dict(_full_config(board_and_agents={"axis_start_index": 1}))


def test_default_origin_and_index_base_are_accepted():
    config = GameConfig.from_dict(_full_config())
    assert config.origin == "top-left"
    assert config.index_base == 0


def test_negative_response_timeout_is_rejected():
    # PRD 2 (§0): a nonsensical deadline must fail at load time, same
    # pattern as PRD 1's numeric validation.
    with pytest.raises(ValueError, match="response_timeout_sec"):
        GameConfig.from_dict(_full_config(network_and_league={"response_timeout_sec": -5}))


def test_zero_watchdog_threshold_is_rejected():
    with pytest.raises(ValueError, match="watchdog_timeout_sec"):
        GameConfig.from_dict(_full_config(network_and_league={"watchdog_timeout_sec": 0}))


def test_fractional_timeout_is_accepted():
    # Unlike board_size/quota/score fields, timeouts may be sub-second —
    # useful for keeping the test suite itself fast.
    config = GameConfig.from_dict(_full_config(network_and_league={"response_timeout_sec": 0.5}))
    assert config.response_timeout_seconds == 0.5


def test_non_string_arena_is_rejected():
    with pytest.raises(ValueError, match="map_area"):
        GameConfig.from_dict(_full_config(world={"map_area": 42}))


def test_empty_arena_is_accepted():
    # Table 14 #1: "" is the documented "generic landmarks" carve-out, not
    # an invalid value — a non-empty validator here would be wrong.
    config = GameConfig.from_dict(_full_config(world={"map_area": ""}))
    assert config.arena == ""


def test_zero_hint_word_limit_is_rejected():
    with pytest.raises(ValueError, match="hint_max_words"):
        GameConfig.from_dict(_full_config(world={"hint_max_words": 0}))


def test_negative_scent_source_strength_is_rejected():
    with pytest.raises(ValueError, match="pheromone_center_intensity"):
        GameConfig.from_dict(_full_config(pheromones={"pheromone_center_intensity": -0.1}))


def test_negative_scent_decay_rate_is_rejected():
    with pytest.raises(ValueError, match="pheromone_decay"):
        GameConfig.from_dict(_full_config(pheromones={"pheromone_decay": -0.1}))


def test_zero_scent_field_size_is_rejected():
    with pytest.raises(ValueError, match="pheromone_grid_size"):
        GameConfig.from_dict(_full_config(pheromones={"pheromone_grid_size": 0}))
