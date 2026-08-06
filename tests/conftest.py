"""Shared fixtures across layers — one config, reused instead of rebuilt per test."""

from __future__ import annotations

import pytest

from cop.shared.config import GameConfig


@pytest.fixture
def config() -> GameConfig:
    return GameConfig(
        board_size=7,
        agent_count=2,
        origin="top-left",
        index_base=0,
        thief_start=(3, 3),
        cop_start=(0, 0),
        barrier_quota=14,
        step_ceiling=35,
        survival_threshold=35,
        score_capture_cop=20,
        score_capture_thief=5,
        score_survival_cop=5,
        score_survival_thief=10,
        score_draw=2,
        response_timeout_seconds=30.0,
        watchdog_threshold_seconds=60.0,
    )
