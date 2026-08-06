"""reasoning/subgame.py: the local, network-free milestone loop.

`run_local_subgame` is what the PRD 3 milestone and every algorithm-
correctness claim run against — no Orchestrator, no network, no subprocess.
"""

from __future__ import annotations

from greedy_thief_mover import greedy_thief_move

from cop.domain.board import Board
from cop.domain.scoring import Outcome
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.subgame import run_local_subgame
from cop.shared.config import GameConfig


def _stay(own_pos, board, barriers) -> str:
    return "STAY"


def test_on_turn_hook_fires_once_per_round_and_is_optional(config):
    board = Board(size=config.board_size)
    calls = []

    outcome = run_local_subgame(
        CopBrain(), _stay, board, config, on_turn=lambda *args: calls.append(args)
    )

    assert outcome == Outcome.CAPTURE
    assert len(calls) >= 1
    first_round, first_action, *_ = calls[0]
    assert first_round == 1
    assert first_action is not None


def test_reaches_capture_against_a_static_known_target(config):
    board = Board(size=config.board_size)

    outcome = run_local_subgame(CopBrain(), _stay, board, config)

    assert outcome == Outcome.CAPTURE


def test_reaches_capture_against_the_moving_greedy_thief_fixture(config):
    # The thief actively evades (prefers cells with more escape routes) —
    # capture here proves genuine pursuit against a non-trivial target, not
    # just a first-move coincidence.
    board = Board(size=config.board_size)

    outcome = run_local_subgame(CopBrain(), greedy_thief_move, board, config)

    assert outcome == Outcome.CAPTURE


def test_stops_at_the_step_ceiling_with_survival_when_capture_never_happens(config):
    board = Board(size=config.board_size)
    tiny_ceiling = config.__class__(
        **{**config.__dict__, "step_ceiling": 1, "survival_threshold": 1}
    )

    outcome = run_local_subgame(CopBrain(), _stay, board, tiny_ceiling)

    assert outcome == Outcome.SURVIVAL


def test_capture_wins_even_on_the_exact_ceiling_turn():
    # A static target from the default start positions is captured on round
    # 6 (verified by direct reproduction) — set the ceiling to exactly that
    # round so both conditions are true simultaneously, and confirm capture
    # still wins, exercised through the real loop, not just the pure
    # determine_outcome unit test from PRD 1.
    config = GameConfig(
        board_size=7,
        agent_count=2,
        origin="top-left",
        index_base=0,
        thief_start=(3, 3),
        cop_start=(0, 0),
        barrier_quota=14,
        step_ceiling=6,
        survival_threshold=6,
        score_capture_cop=20,
        score_capture_thief=5,
        score_survival_cop=5,
        score_survival_thief=10,
        score_draw=2,
        response_timeout_seconds=30.0,
        watchdog_threshold_seconds=60.0,
    )
    board = Board(size=config.board_size)

    outcome = run_local_subgame(CopBrain(), _stay, board, config)

    assert outcome == Outcome.CAPTURE
