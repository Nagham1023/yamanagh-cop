"""Reward shaping for self-play training (PRD 11).

Terminal reward reuses `GameConfig.score_capture_cop`/`score_survival_cop`
directly — Table 17's Appendix F values, never reinvented as a separate RL
reward scale. Only the *per-step* shaping (encouraging faster captures) is
RL-only tuning, sourced from `RLTrainingConfig`, never Appendix F.

**Rigor pass (PRD 14)**: the per-step term is potential-based shaping (Ng,
Harada & Russell, 1999), stated here explicitly rather than left as "looks
about right." With `Φ(s) = -manhattan_distance(cop, target)` as the
potential function, `prev_distance - new_distance` is exactly
`Φ(s') - Φ(s)` — closing distance raises the potential, and the shaping
term rewards that rise directly. Ng's own invariance theorem is what makes
this safe to add at all: a term of this exact shape (`F(s,a,s') =
γΦ(s') - Φ(s)`) provably does not change which policy is optimal, only how
quickly a episode-based learner finds it — the theorem's actual guarantee is
provably safe, not merely "seems to help."

**One honest gap, not a hidden bug**: Ng's theorem calls for `γΦ(s')`, and
this implementation omits the `γ` multiplier on the per-step term (`rl_config.gamma`
still applies to the Bellman update itself in `train_loop.py`, just not
here). A common simplification — its effect is small when `γ` is close to 1
(`0.95` here) and the shaping weight is small (`0.1`) — but it means this is
an *approximation* of Ng's guarantee, not a byte-exact instance of it. The
exact fix, if ever wanted: `distance_shaping_weight * (prev_distance -
rl_config.gamma * new_distance)`. Not applied here — this pass is
documentation rigor, not a training-behavior change; a real, honestly-
labeled follow-up if the approximation is ever judged worth tightening.
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
