"""Reward shaping for self-play training (PRD 11).

Terminal reward reuses `GameConfig.score_capture_cop`/`score_survival_cop`
directly — Table 17's Appendix F values, never reinvented as a separate RL
reward scale. Only the *per-step* shaping (encouraging faster captures) is
RL-only tuning, sourced from `RLTrainingConfig`, never Appendix F.
"""

from __future__ import annotations

from cop.domain.scoring import Outcome
from cop.shared.config import GameConfig

from .config import RLTrainingConfig


def step_reward(
    *,
    prev_distance: int,
    new_distance: int,
    outcome: Outcome | None,
    game_config: GameConfig,
    rl_config: RLTrainingConfig,
) -> float:
    """`outcome` is `None` while the episode is still in progress — the
    common case, shaped by distance closed this step minus a small step
    cost. A terminal `outcome` overrides shaping entirely with the real
    Table 17 score, since the game's own scoring is a stronger, more
    honest signal than any hand-tuned shaping term."""
    if outcome is Outcome.CAPTURE:
        return float(game_config.score_capture_cop)
    if outcome is Outcome.SURVIVAL:
        return float(game_config.score_survival_cop)
    if outcome is Outcome.TECHNICAL_LOSS:
        return 0.0
    shaping = rl_config.distance_shaping_weight * (prev_distance - new_distance)
    return shaping - rl_config.step_cost
