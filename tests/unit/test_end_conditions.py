"""End-of-subgame determination: capture precedence, thresholds, and in-progress."""

from __future__ import annotations

from cop.domain.end_conditions import determine_outcome
from cop.domain.scoring import Outcome


def test_game_in_progress_returns_none():
    result = determine_outcome(
        captured=False, steps_taken=10, step_ceiling=35, survival_threshold=35
    )
    assert result is None


def test_capture_ends_the_game_immediately():
    result = determine_outcome(
        captured=True, steps_taken=3, step_ceiling=35, survival_threshold=35
    )
    assert result is Outcome.CAPTURE


def test_capture_takes_precedence_over_reaching_the_threshold_same_turn():
    result = determine_outcome(
        captured=True, steps_taken=35, step_ceiling=35, survival_threshold=35
    )
    assert result is Outcome.CAPTURE


def test_reaching_survival_threshold_without_capture_is_survival():
    result = determine_outcome(
        captured=False, steps_taken=35, step_ceiling=35, survival_threshold=35
    )
    assert result is Outcome.SURVIVAL


def test_reaching_step_ceiling_without_capture_is_survival():
    result = determine_outcome(
        captured=False, steps_taken=40, step_ceiling=35, survival_threshold=50
    )
    assert result is Outcome.SURVIVAL
