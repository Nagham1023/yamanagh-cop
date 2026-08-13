"""The 20-seed ensemble stage (PRD 14 round-2 post-gate) — trains many
independent seeds, keeps the ones that actually learned belief-aware
traversal, and majority-vote-combines their Q-tables into one checkpoint.

Follows `refinement_loop.py`'s own `{prefix}_round{N}` shape for a new,
genuinely different case: many *independent* seeds, not one sequentially-
growing search. Every per-seed run gets its own full `training/runs/
{prefix}_seed{k}/` artifact directory via the *unmodified* `stages.run_train`/
`evaluate_stages.run_evaluate*` — nothing here special-cases per-seed
training, only the selection and merge steps that follow it are new.

**Selection metric**: `win_rate_vs_baseline_belief_aware`, not the plain
ground-truth `win_rate_vs_baseline` — "did this seed learn belief-aware
traversal" is literally what the user's own proposal asked to filter on,
and it's what this whole layer exists to improve.

**Merge policy**: `a* = argmax_a Σ_k Q_k(s,a)` summed only over the tables
that actually contain a given `(state, action)` pair — a state one of the
five seeds never visited contributes nothing to that state's sum, rather
than being treated as a real `0.0` vote that would unfairly punish an
action every other table scored highly. `quantize_q_table_per_row`/
`argmax_agreement_rate` (`training/quantize.py`) are pure functions of a
`dict[State, dict[str, float]]` and need no changes to operate on the
merged table — confirmed by reading them, not assumed from the formula's
shape alone.
"""

from __future__ import annotations

import dataclasses

from cop.reasoning.rl_checkpoint import State, load_checkpoint, save_checkpoint
from cop.shared.config import GameConfig

from ..config import RLTrainingConfig
from . import artifacts, stages
from .evaluate_stages import run_evaluate_belief_aware


def run_ensemble(
    game_config: GameConfig,
    base_rl_config: RLTrainingConfig,
    run_id_prefix: str,
    game_config_path: str,
    *,
    seed_count: int = 20,
    keep_count: int = 5,
) -> dict:
    """Trains `seed_count` independent seeds, ranks by belief-aware win-rate,
    keeps the top `keep_count` (a strict subset of the top half by
    construction — logged explicitly below, not implemented as two
    independent filters), merges their Q-tables, and runs the existing
    quantize/benchmark/evaluate stages against the result exactly like any
    other checkpoint."""
    ranking: list[dict] = []
    for seed in range(seed_count):
        run_id = f"{run_id_prefix}_seed{seed}"
        seed_rl_config = dataclasses.replace(base_rl_config, seed=seed)
        stages.run_train(game_config, seed_rl_config, run_id, game_config_path)
        stages.run_evaluate(game_config, run_id)
        belief_aware = run_evaluate_belief_aware(game_config, seed_rl_config, run_id)
        ranking.append({
            "seed": seed,
            "run_id": run_id,
            "win_rate_vs_baseline_belief_aware": belief_aware["win_rate_vs_baseline_belief_aware"],
        })

    ranking = _rank_and_select(ranking, keep_count)
    bottom_half_size = seed_count - seed_count // 2  # "dropped" count, for the log below
    selected = ranking[:keep_count]

    merged = _merge_q_tables([row["run_id"] for row in selected])
    ensemble_run_id = f"{run_id_prefix}_ensemble"
    save_checkpoint(artifacts.checkpoint_path(ensemble_run_id), merged)

    quantize_result = stages.run_quantize(ensemble_run_id)
    benchmark_result = stages.run_benchmark(game_config, base_rl_config, ensemble_run_id)
    evaluate_result = stages.run_evaluate(game_config, ensemble_run_id)
    belief_aware_result = run_evaluate_belief_aware(game_config, base_rl_config, ensemble_run_id)

    payload = {
        "seed_count": seed_count,
        "keep_count": keep_count,
        "ranking": ranking,
        "selected_run_ids": [row["run_id"] for row in selected],
        "top_keep_count_is_subset_of_bottom_half_survivors": keep_count <= bottom_half_size,
        "merge_policy": "sum Q(s,a) only over tables that visited (s,a); missing is no vote, not zero",
        "ensemble_run_id": ensemble_run_id,
        "ensemble_win_rate_vs_baseline": evaluate_result["win_rate_vs_baseline"],
        "ensemble_win_rate_vs_baseline_belief_aware": belief_aware_result[
            "win_rate_vs_baseline_belief_aware"
        ],
        "ensemble_argmax_agreement_rate": quantize_result["argmax_agreement_rate"],
        "ensemble_margin_multiple": benchmark_result["margin_multiple"],
        "best_single_seed_win_rate_vs_baseline_belief_aware": ranking[0][
            "win_rate_vs_baseline_belief_aware"
        ],
    }
    artifacts.write_stage_metrics(run_id_prefix, "ensemble", payload)
    return payload


def _rank_and_select(ranking: list[dict], keep_count: int) -> list[dict]:
    """Sorted descending by belief-aware win-rate — a plain top-`keep_count`
    slice is always a subset of the top half by construction (never
    implemented as two independent filters), which `run_ensemble` logs
    explicitly via `top_keep_count_is_subset_of_bottom_half_survivors`."""
    return sorted(ranking, key=lambda row: row["win_rate_vs_baseline_belief_aware"], reverse=True)


def _merge_q_tables(run_ids: list[str]) -> dict[State, dict[str, float]]:
    merged: dict[State, dict[str, float]] = {}
    for run_id in run_ids:
        q_values = load_checkpoint(artifacts.checkpoint_path(run_id)).as_dict()
        for state, action_values in q_values.items():
            row = merged.setdefault(state, {})
            for action, value in action_values.items():
                row[action] = row.get(action, 0.0) + value
    return merged
