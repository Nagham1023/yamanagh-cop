"""The pipeline stages (PRD 13): train, evaluate, quantize, benchmark.

Each is a thin wire into `training/`'s own PRD-11/12 functions, writing
exactly one structured artifact via `artifacts.write_stage_metrics` — no
stage re-derives another stage's numbers, matching PLAN.md §6's scope-
partitioning responsibility.

`run_evaluate`/`run_evaluate_belief_aware` (PRD 14 sub-layer A) live in
`evaluate_stages.py`, split out once that pair pushed this file past the
150-line house cap — re-exported here so every existing caller
(`orchestrate_pipeline.py`, `refinement_loop.py`) keeps calling
`stages.run_evaluate` unchanged.
"""

from __future__ import annotations

from cop.domain.board import Board
from cop.reasoning.rl_checkpoint import load_checkpoint, save_checkpoint
from cop.reasoning.rl_cop_brain import RLCopBrain
from cop.shared.config import GameConfig

from ..benchmark_latency import benchmark_pick_move_latency, sample_realistic_states
from ..checkpoint_io import save
from ..config import RLTrainingConfig
from ..opponent_policies import greedy_escape_thief
from ..quantize import argmax_agreement_rate, quantize_q_table_per_row
from ..train_loop import train
from . import artifacts
from .evaluate_stages import _EVAL_SEED, run_evaluate, run_evaluate_belief_aware

__all__ = [
    "run_train", "run_evaluate", "run_evaluate_belief_aware", "run_quantize", "run_benchmark",
]

_BENCHMARK_SAMPLE_COUNT = 5000


def run_train(
    game_config: GameConfig, rl_config: RLTrainingConfig, run_id: str, game_config_path: str
) -> dict:
    q_table, metrics = train(game_config, rl_config)
    save(artifacts.checkpoint_path(run_id), q_table)
    payload = {
        "episode_count": metrics.episode_count,
        "final_epsilon": metrics.final_epsilon,
        "reward_history": list(metrics.reward_history),
        "states_visited": len(q_table.as_dict()),
    }
    artifacts.write_stage_metrics(run_id, "train", payload)
    artifacts.write_provenance(run_id, rl_config, game_config_path)
    return payload


def run_quantize(run_id: str) -> dict:
    table = load_checkpoint(artifacts.checkpoint_path(run_id))
    q_values = table.as_dict()
    quantized, params = quantize_q_table_per_row(q_values)  # PRD 14: per-row, not per-table
    save_checkpoint(artifacts.quantized_checkpoint_path(run_id), quantized, quantization=params)

    size_before = artifacts.checkpoint_path(run_id).stat().st_size
    size_after = artifacts.quantized_checkpoint_path(run_id).stat().st_size
    payload = {
        "argmax_agreement_rate": argmax_agreement_rate(q_values, quantized, params),
        "size_before_bytes": size_before,
        "size_after_bytes": size_after,
        "size_reduction_fraction": 1 - size_after / size_before if size_before else 0.0,
    }
    artifacts.write_stage_metrics(run_id, "quantize", payload)
    return payload


def run_benchmark(game_config: GameConfig, rl_config: RLTrainingConfig, run_id: str) -> dict:
    board = Board(size=game_config.board_size)
    samples = sample_realistic_states(
        board, game_config, rl_config, greedy_escape_thief, _BENCHMARK_SAMPLE_COUNT, seed=_EVAL_SEED
    )
    quantized_path = artifacts.quantized_checkpoint_path(run_id)
    checkpoint_used = quantized_path if quantized_path.exists() else artifacts.checkpoint_path(run_id)
    brain = RLCopBrain(checkpoint_path=checkpoint_used)
    result = benchmark_pick_move_latency(brain, samples)

    margin = game_config.response_timeout_seconds / result.p99_seconds if result.p99_seconds > 0 else None
    payload = {
        "p50_seconds": result.p50_seconds,
        "p95_seconds": result.p95_seconds,
        "p99_seconds": result.p99_seconds,
        "sample_count": result.sample_count,
        "response_timeout_seconds": game_config.response_timeout_seconds,
        "margin_multiple": margin,
    }
    artifacts.write_stage_metrics(run_id, "benchmark", payload)
    return payload
