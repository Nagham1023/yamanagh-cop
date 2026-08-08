"""TODO1.md #2: prove config values actually drive domain behaviour, end-to-end.

Every other test constructs `Board`/`BarrierSet` directly with a literal —
which proves the domain logic is correct, but never proves the *pipeline*
from `config/shared/config_dev_g01.json` into that logic is wired up at all.
Invariant I6 promises "every quantitative value comes from config"; these
tests are what actually backs that promise instead of just the absence of
a hardcoded literal in the source.
"""

from __future__ import annotations

import json

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.shared.config import GameConfig

REPO_CONFIG = "config/shared/config_dev_g01.json"


def test_board_size_from_config_drives_bounds_checking():
    config = GameConfig.from_file(REPO_CONFIG)
    board = Board(size=config.board_size)

    # The dev config's board_size is 7 — the last valid column/row is index 6.
    assert board.in_bounds(Position(config.board_size - 1, config.board_size - 1)) is True
    assert board.in_bounds(Position(config.board_size, 0)) is False


def test_barrier_quota_from_config_drives_quota_rejection(tmp_path):
    # A quota of 1, loaded from a file rather than passed as a literal, must
    # be the number that actually stops the second placement.
    custom = {
        "schema_version": "1.2",
        "agreed_between": ["group-a", "group-b"],
        "board_and_agents": {
            "grid_size": 7, "num_agents": 2, "thief_start": [3, 3], "cop_start": [0, 0],
            "axis_origin_corner": "top-left", "axis_start_index": 0,
        },
        "world": {"map_area": "New York", "hint_max_words": 15},
        "movement_and_barriers": {
            "move_set": ["N", "S", "E", "W", "STAY"],
            "max_barriers": 1, "max_moves": 35, "survival_threshold": 35,
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
    path = tmp_path / "config_quota_one.json"
    path.write_text(json.dumps(custom), encoding="utf-8")

    config = GameConfig.from_file(path)
    board = Board(size=config.board_size)
    barriers = BarrierSet(quota=config.barrier_quota)

    assert barriers.place(Position(0, 0), Position(0, 0), board=board) is True
    assert barriers.place(Position(0, 0), Position(0, 1), board=board) is False


def test_barrier_quota_exactly_14_from_config_and_15th_is_refused():
    """Backs scripts/watch_barrier_placements.py: not a scaled-down quota
    (test_barrier_beyond_quota_is_rejected uses quota=2 for speed) — this is
    the real config value, 14 distinct legal placements, then a refusal."""
    config = GameConfig.from_file(REPO_CONFIG)
    assert config.barrier_quota == 14

    board = Board(size=config.board_size)
    barriers = BarrierSet(quota=config.barrier_quota)

    # 14 distinct, legal cells: a barrier on the cop's own current cell,
    # walking row 0 then back along row 1.
    path = [Position(col, 0) for col in range(board.size)]
    path += [Position(col, 1) for col in reversed(range(board.size))]
    assert len(path) == config.barrier_quota  # sanity: this path is exactly 14 cells

    for cell in path:
        assert barriers.place(cop_pos=cell, target=cell, board=board) is True

    assert len(barriers.placed) == config.barrier_quota

    fifteenth = Position(0, 2)  # fresh, otherwise-legal cell
    assert barriers.place(cop_pos=fifteenth, target=fifteenth, board=board) is False
    assert len(barriers.placed) == config.barrier_quota  # refusal left the count unchanged
