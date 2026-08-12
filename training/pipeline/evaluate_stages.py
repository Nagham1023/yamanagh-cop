"""The `evaluate` pipeline stage — split out of `stages.py` once PRD 14 sub-
layer A's additive belief-aware companion pushed that file past the
150-line house cap. `stages.py` re-exports both functions here so every
existing caller (`stages.run_evaluate`, `orchestrate_pipeline.py`,
`refinement_loop.py`) keeps working unchanged.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from cop.domain.board import Board
from cop.domain.scoring import Outcome
from cop.reasoning.brain_base import BrainBase
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.rl_cop_brain import RLCopBrain
from cop.reasoning.subgame import run_local_subgame
from cop.shared.config import GameConfig

from ..config import RLTrainingConfig
from ..env import SelfPlayEnv
from ..opponent_policies import make_random_walk_thief
from . import artifacts

_EVAL_EPISODES = 200  # PRD 14 follow-up: 20 was too thin for a confident win-rate margin
_EVAL_SEED = 20260812


def run_evaluate(game_config: GameConfig, run_id: str) -> dict:
    """Win-rate vs. baseline `CopBrain`, both against the same seeded
    random-walk thief opponents per episode — the coverage criterion
    `refinement_loop.py` reads is `win_rate_vs_baseline`. Ground-truth by
    design (`run_local_subgame`, PRD-4's own decision) — see
    `run_evaluate_belief_aware` for the belief-aware companion."""
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


def run_evaluate_belief_aware(
    game_config: GameConfig, rl_config: RLTrainingConfig, run_id: str
) -> dict:
    """Additive companion to `run_evaluate` (PRD 14 sub-layer A): that stage
    drives both brains through ground-truth `run_local_subgame` (PRD-4's own
    decision, `subgame.py` untouched), so it never exercises the belief-based
    states sub-layer A trains for. This reuses belief-tracking `SelfPlayEnv`
    instead, driven greedily through each brain's own `_pick_move`, and
    writes additively into the *same* `evaluate_metrics.json` — nothing
    existing renamed or removed, `ml-promotion-gate`'s checklist unaffected."""
    board = Board(size=game_config.board_size)
    rl_rate, rl_avg_steps = _belief_aware_capture_stats(
        lambda confidence_fn: RLCopBrain(
            checkpoint_path=artifacts.checkpoint_path(run_id), belief_confidence_provider=confidence_fn
        ),
        board, game_config, rl_config,
    )
    baseline_rate, baseline_avg_steps = _belief_aware_capture_stats(
        lambda _confidence_fn: CopBrain(), board, game_config, rl_config
    )
    payload_update = {
        "win_rate_vs_baseline_belief_aware": rl_rate,
        "rl_capture_rate_belief_aware": rl_rate,
        "rl_avg_steps_to_capture_belief_aware": rl_avg_steps,
        "baseline_capture_rate_belief_aware": baseline_rate,
        "baseline_avg_steps_to_capture_belief_aware": baseline_avg_steps,
    }
    existing = (
        artifacts.read_stage_metrics(run_id, "evaluate")
        if artifacts.stage_metrics_exist(run_id, "evaluate")
        else {}
    )
    existing.update(payload_update)
    artifacts.write_stage_metrics(run_id, "evaluate", existing)
    return payload_update


def _belief_aware_capture_stats(
    brain_factory: Callable[[Callable[[], float]], BrainBase],
    board: Board,
    game_config: GameConfig,
    rl_config: RLTrainingConfig,
) -> tuple[float, float | None]:
    """`brain_factory` receives one argument — a zero-arg confidence
    callable bound to whichever `SelfPlayEnv` instance is driving that
    episode — so an `RLCopBrain` factory can pass it straight through as
    its own `belief_confidence_provider` and genuinely exercise every
    confidence bucket the checkpoint learned, not just the default. A
    `CopBrain` factory simply ignores the argument (no Q-table to query)."""
    rng = random.Random(_EVAL_SEED)
    captures = 0
    capture_steps: list[int] = []
    for _ in range(_EVAL_EPISODES):
        thief_mover = make_random_walk_thief(random.Random(rng.random()))
        env = SelfPlayEnv(board, game_config, rl_config, thief_mover)
        env.reset()
        brain = brain_factory(lambda env=env: env._belief.believed_target()[1])

        done = False
        outcome = None
        steps = 0
        while not done:
            believed_pos, _confidence = env._belief.believed_target()
            direction = brain._pick_move(env.cop_pos, believed_pos, env._board, env._barriers)
            _next_state, _reward, done, outcome = env.step(direction)
            steps += 1
        if outcome is Outcome.CAPTURE:
            captures += 1
            capture_steps.append(steps)
    capture_rate = captures / _EVAL_EPISODES
    avg_steps = sum(capture_steps) / len(capture_steps) if capture_steps else None
    return capture_rate, avg_steps
