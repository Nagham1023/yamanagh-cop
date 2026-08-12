"""The bounded train/eval refinement cycle (PRD 13) — PLAN.md §6's
non-negotiable requirement, applied explicitly: a hard iteration cap, an
explicit numeric coverage criterion (never "looks good enough"), and a
wall-clock budget checked *before* each round starts, not only after.

This is a second, independent instance of PLAN §6's bounded-loop
discipline — distinct from that section's own between-game opponent-
modeling coordinator (if that optional layer is ever built too). Agents
are invoked once each, at defined gate points after this loop converges
or caps out — never inside the loop itself, which keeps "the textbook case
the book warns about" (an unbounded agent-side refinement loop)
structurally absent here, not merely bounded.
"""

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass, field

from cop.shared.config import GameConfig

from ..config import RLTrainingConfig
from . import stages
from .artifacts import write_stage_metrics


@dataclass(frozen=True)
class RefinementResult:
    best_run_id: str | None
    rounds_run: int
    converged: bool
    refinement_log: tuple[dict, ...] = field(default_factory=tuple)


def run_train_eval_cycle(
    game_config: GameConfig, rl_config: RLTrainingConfig, run_id_prefix: str
) -> RefinementResult:
    """Each failing round doubles `episode_count` — one fixed, documented
    rule, never an LLM call or a judgement inside the loop. Returns the
    *best* round's checkpoint if the cap is exhausted without meeting the
    target, never the last one blindly — "a merely adequate model is
    always cheaper than the loop not returning" (PLAN.md §6, verbatim).

    Persists its own result via `write_stage_metrics(run_id_prefix,
    "refinement", ...)` before returning, either path — so `ml-promotion-gate`
    (or any other reader) can find the search's outcome on disk without
    re-running it."""
    start = time.monotonic()
    log: list[dict] = []
    best_run_id: str | None = None
    best_win_rate = -1.0
    cfg = rl_config
    converged = False
    round_number = 0

    for round_number in range(1, rl_config.max_refinement_rounds + 1):
        if time.monotonic() - start >= rl_config.wall_clock_budget_seconds:
            round_number -= 1  # this round never actually ran
            break

        run_id = f"{run_id_prefix}_round{round_number}"
        stages.run_train(game_config, cfg, run_id)
        eval_result = stages.run_evaluate(game_config, run_id)
        win_rate = eval_result["win_rate_vs_baseline"]
        log.append({"round": round_number, "episode_count": cfg.episode_count, "win_rate": win_rate})

        if win_rate > best_win_rate:
            best_win_rate = win_rate
            best_run_id = run_id
        if win_rate >= rl_config.win_rate_target:
            converged = True
            break
        cfg = dataclasses.replace(cfg, episode_count=cfg.episode_count * 2)

    result = RefinementResult(
        best_run_id=best_run_id, rounds_run=round_number, converged=converged, refinement_log=tuple(log)
    )
    write_stage_metrics(
        run_id_prefix,
        "refinement",
        {
            "best_run_id": result.best_run_id,
            "rounds_run": result.rounds_run,
            "converged": result.converged,
            "refinement_log": list(result.refinement_log),
        },
    )
    return result
