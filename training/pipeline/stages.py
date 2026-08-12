"""The four pipeline stages (PRD 13): train, evaluate, quantize, benchmark.

Each is a thin wire into `training/`'s own PRD-11/12 functions, writing
exactly one structured artifact via `artifacts.write_stage_metrics` — no
stage re-derives another stage's numbers, matching PLAN.md §6's scope-
partitioning responsibility.
"""

from __future__ import annotations

import random

from cop.domain.board import Board
from cop.domain.scoring import Outcome
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.rl_checkpoint import load_checkpoint, save_checkpoint
from cop.reasoning.rl_cop_brain import RLCopBrain
from cop.reasoning.subgame import run_local_subgame
from cop.shared.config import GameConfig

from ..benchmark_latency import benchmark_pick_move_latency, sample_realistic_states
from ..checkpoint_io import save
from ..config import RLTrainingConfig
from ..opponent_policies import greedy_escape_thief, make_random_walk_thief
from ..quantize import argmax_agreement_rate, quantize_q_table
from ..train_loop import train
from . import artifacts

_EVAL_EPISODES = 20
_EVAL_SEED = 20260812
_BENCHMARK_SAMPLE_COUNT = 5000


def run_train(game_config: GameConfig, rl_config: RLTrainingConfig, run_id: str) -> dict:
    q_table, metrics = train(game_config, rl_config)
    save(artifacts.checkpoint_path(run_id), q_table)
    payload = {
        "episode_count": metrics.episode_count,
        "final_epsilon": metrics.final_epsilon,
        "reward_history": list(metrics.reward_history),
        "states_visited": len(q_table.as_dict()),
    }
    artifacts.write_stage_metrics(run_id, "train", payload)
    return payload


def run_evaluate(game_config: GameConfig, run_id: str) -> dict:
    """Win-rate vs. baseline `CopBrain`, both against the same seeded
    random-walk thief opponents per episode — the coverage criterion
    `refinement_loop.py` reads is `win_rate_vs_baseline`."""
    board = Board(size=game_config.board_size)
    rl_rate, rl_avg_steps = _capture_stats(
        lambda: RLCopBrain(checkpoint_path=artifacts.checkpoint_path(run_id)), board, game_config
    )
    baseline_rate, baseline_avg_steps = _capture_stats(lambda: CopBrain(), board, game_config)
    payload = {
        "episodes": _EVAL_EPISODES,
        "rl_capture_rate": rl_rate,
        "rl_avg_steps_to_capture": rl_avg_steps,
        "baseline_capture_rate": baseline_rate,
        "baseline_avg_steps_to_capture": baseline_avg_steps,
        "win_rate_vs_baseline": rl_rate,
    }
    artifacts.write_stage_metrics(run_id, "evaluate", payload)
    return payload


def _capture_stats(
    brain_factory, board: Board, game_config: GameConfig
) -> tuple[float, float | None]:
    rng = random.Random(_EVAL_SEED)
    captures = 0
    capture_steps: list[int] = []
    for _ in range(_EVAL_EPISODES):
        thief_mover = make_random_walk_thief(random.Random(rng.random()))
        steps_taken = {"n": 0}

        def _count(round_number, _action, _cop_pos, _thief_pos, _barriers, _n=steps_taken):
            _n["n"] = round_number

        outcome = run_local_subgame(brain_factory(), thief_mover, board, game_config, on_turn=_count)
        if outcome is Outcome.CAPTURE:
            captures += 1
            capture_steps.append(steps_taken["n"])
    capture_rate = captures / _EVAL_EPISODES
    avg_steps = sum(capture_steps) / len(capture_steps) if capture_steps else None
    return capture_rate, avg_steps


def run_quantize(run_id: str) -> dict:
    table = load_checkpoint(artifacts.checkpoint_path(run_id))
    q_values = table.as_dict()
    quantized, params = quantize_q_table(q_values)
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
