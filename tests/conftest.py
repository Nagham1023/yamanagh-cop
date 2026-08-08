"""Shared fixtures across layers — one config, reused instead of rebuilt per test.

Also puts `tests/support/` on `sys.path`: it holds test/demo scaffolding
(e.g. `greedy_thief_mover.py`, PRD 3 Design Question 5) that unit tests in
other directories need to import, unlike `tests/integration/`'s own
same-directory helpers which pytest's default rootdir insertion already
covers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from cop.shared.config import GameConfig

sys.path.insert(0, str(Path(__file__).parent / "support"))


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
        arena="New York",
        hint_word_limit=15,
        scent_source_strength=0.9,
        scent_decay_rate=0.10,
        scent_field_size=5,
        schema_version="1.2",
        agreed_between=("group-a", "group-b"),
        token_budget_per_series=200_000,
        rate_limit_requests_per_minute=30.0,
        rate_limit_concurrent_requests=2,
        rate_limit_retry_backoff_seconds=5.0,
        rate_limit_max_retries=3,
        rate_limit_queue_depth=100,
    )
