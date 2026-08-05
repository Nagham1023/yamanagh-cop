"""Scoring for a single sub-game (Table 17): capture, survival, or technical loss.

Every value here comes from `GameConfig`, never a literal — a hard-coded 20
or 5 would be exactly the "magic number" invariant I6 exists to forbid.
Series-level aggregation (the draw score across six sub-games) is a
reporting-layer concern (PRD 7), not this module's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..shared.config import GameConfig


class Outcome(Enum):
    CAPTURE = "capture"
    SURVIVAL = "survival"
    TECHNICAL_LOSS = "technical_loss"


@dataclass(frozen=True)
class Score:
    cop: int
    thief: int


def score_outcome(outcome: Outcome, config: GameConfig) -> Score:
    """Table 17: map an end-of-subgame outcome to the (cop, thief) score pair."""
    if outcome is Outcome.CAPTURE:
        return Score(config.score_capture_cop, config.score_capture_thief)
    if outcome is Outcome.SURVIVAL:
        return Score(config.score_survival_cop, config.score_survival_thief)
    return Score(0, 0)  # technical loss: 0 to both sides, no exceptions (Table 17)
