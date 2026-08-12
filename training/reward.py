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

**`barrier_restriction_bonus_weight` (PRD 14 post-gate follow-up) — a flat
bonus, NOT potential-based, NOT provably policy-invariant.** Applied only on
a step where the chosen action is itself a barrier placement that restricts
the *believed* target's escape routes (`env.py::step` computes this via
`CopBrain._restricts_target` against the belief target captured before the
action, never a passive per-state bonus for merely standing in an enclosing
position — `enclosure_bucket` already encodes that as a state feature, and
a passive bonus would let the agent farm reward by loitering near a corner
without ever placing a barrier). Built only after `training/pipeline/
barrier_restriction_metric.py` measured a real, honest gap on the trained
checkpoint (14.8% of barrier-top-ranked states restricted the believed
target — most learned barrier placements were incidental, not purposeful).
Unlike `distance_shaping_weight`'s term above, this bonus's shape is
`+weight` on one specific action, not `F(s,a,s') = γΦ(s') − Φ(s)` for any
potential function `Φ` — Ng/Harada/Russell's invariance theorem does not
cover it. It is a heuristic approximation, and the predicted risk (bias
toward premature/wasteful barrier placements) is not hypothetical — a real
`weight=0.5` run collapsed belief-aware win-rate to 0.00 (from a 0.24
pre-bonus baseline), the exact failure this docstring warned about before
it was built. **`0.1` is the current default, chosen from a real, seed-
controlled sweep, not a guess**: the same 5 seeds run at `weight=0.0` vs.
`weight=0.1` (holding everything else fixed) show `0.1` roughly doubling
the average belief-aware win-rate (0.112 -> 0.272 across seeds 0-4) with no
ground-truth win-rate cost — but individual seeds still range 0.00-0.48,
real variance this small a tabular setup doesn't fully average out. Full
sweep recorded in `TODO.md`'s PRD 14 entry. Any future retuning of this
weight should re-run that same controlled comparison, not eyeball one seed.
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
    restricts_believed_target: bool = False,
) -> float:
    """`outcome` is `None` while the episode is still in progress — the
    common case, shaped by distance closed this step minus a small step
    cost, plus `barrier_restriction_bonus_weight` when
    `restricts_believed_target` (see the module docstring for why this
    term is NOT the same provably-safe shape as the distance term below
    it). A terminal `outcome` overrides shaping entirely with the real
    Table 17 score, since the game's own scoring is a stronger, more
    honest signal than any hand-tuned shaping term — `restricts_believed_target`
    is deliberately ignored on a terminal step for the same reason."""
    if outcome is Outcome.CAPTURE:
        return float(game_config.score_capture_cop)
    if outcome is Outcome.SURVIVAL:
        return float(game_config.score_survival_cop)
    if outcome is Outcome.TECHNICAL_LOSS:
        return 0.0
    shaping = rl_config.distance_shaping_weight * (prev_distance - new_distance)
    bonus = rl_config.barrier_restriction_bonus_weight if restricts_believed_target else 0.0
    return shaping + bonus - rl_config.step_cost
