"""Board size, barrier quota, and step ceiling are MINIMUMs in Appendix F
(Table 15) — an opponent can legally negotiate them upward (9x9, 11x11,
higher quotas/ceilings). A suite that only ever runs at 7/14/35 has no
evidence CopBrain still works once a real opponent raises them.
"""

from __future__ import annotations

import pytest
from greedy_thief_mover import greedy_thief_move

from cop.domain.board import Board
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.subgame import run_local_subgame
from cop.shared.config import GameConfig

_BASE_BOARD_SIZE = 7
_BASE_BARRIER_QUOTA = 14
_BASE_STEP_CEILING = 35


def _config_for(board_size: int) -> GameConfig:
    scale = board_size / _BASE_BOARD_SIZE
    center = board_size // 2
    ceiling = round(_BASE_STEP_CEILING * scale)
    return GameConfig(
        board_size=board_size,
        agent_count=2,
        origin="top-left",
        index_base=0,
        thief_start=(center, center),
        cop_start=(0, 0),
        barrier_quota=round(_BASE_BARRIER_QUOTA * scale),
        step_ceiling=ceiling,
        survival_threshold=ceiling,
        score_capture_cop=20,
        score_capture_thief=5,
        score_survival_cop=5,
        score_survival_thief=10,
        score_draw=2,
        response_timeout_seconds=30.0,
        watchdog_threshold_seconds=60.0,
        arena="New York",
        hint_word_limit=15,
        scent_source_strength=0.9,
        scent_decay_rate=0.10,
        scent_field_size=5,
        schema_version="1.2",
        agreed_between=("group-a", "group-b"),
    )


def _stay(own_pos, board, barriers) -> str:
    return "STAY"


@pytest.mark.parametrize("board_size", [7, 9, 11])
def test_milestone_captures_a_static_target_at_multiple_board_sizes(board_size):
    config = _config_for(board_size)
    board = Board(size=board_size)

    outcome = run_local_subgame(CopBrain(), _stay, board, config)

    assert outcome.value == "capture"


@pytest.mark.parametrize("board_size", [7, 9, 11])
def test_pursuit_captures_the_moving_greedy_thief_at_multiple_board_sizes(board_size):
    config = _config_for(board_size)
    board = Board(size=board_size)

    outcome = run_local_subgame(CopBrain(), greedy_thief_move, board, config)

    assert outcome.value == "capture"
