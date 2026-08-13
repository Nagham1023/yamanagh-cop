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
from unittest.mock import patch

import pytest

from cop.orchestrator import Orchestrator
from cop.shared.config import GameConfig

sys.path.insert(0, str(Path(__file__).parent / "support"))


@pytest.fixture(autouse=True)
def _stop_watchdog_monitors_after_test():
    """PRD 15's own follow-up finding: `run_as_server`'s watchdog poll
    thread runs for the rest of the process's life by design (rule 7 says
    "run" a watchdog continuously for a live match) — correct in
    production, where one process holds exactly one `Orchestrator` and the
    thread dies with the process at normal exit (rule 1/2). This shared
    pytest process instead constructs hundreds of orchestrators across the
    whole session; once any abandoned one goes >60s stale, its real
    `os._exit(1)` used to kill the entire test run, unrelated to whatever
    test happened to be running by then. Tracks every `Orchestrator`
    constructed during one test and calls its (idempotent, PRD 15)
    `stop_watchdog_monitor()` before the next test starts — a no-op for
    any orchestrator that never called `run_as_server` at all."""
    created: list[Orchestrator] = []
    original_init = Orchestrator.__init__

    def _tracking_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        created.append(self)

    with patch.object(Orchestrator, "__init__", _tracking_init):
        yield
    for orchestrator in created:
        orchestrator.stop_watchdog_monitor()


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
