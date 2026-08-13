"""SelfPlayEnv reproduces run_local_subgame's outcome given the same fixed
movement policy and the same opponent — proves the two are physics-
identical, not a second game engine with its own drift risk.

Comparison uses `barrier_quota=0` so `CopBrain._decide_move` always falls
back to a plain move (its barrier candidates all fail `can_place`'s quota
check) — the same movement-only shape `SelfPlayEnv` implements, since
barrier-placement RL is out of scope (see training/env.py's own docstring).
"""

from __future__ import annotations

import dataclasses
import random

from greedy_thief_mover import greedy_thief_move

from cop.domain.board import Board, Position
from cop.domain.movement import DELTAS
from cop.reasoning.brain_base import Action, Move, PlaceBarrier
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.subgame import run_local_subgame
from training.config import RLTrainingConfig
from training.env import SelfPlayEnv


def _action_to_env_string(action: Action, own_pos: Position) -> str:
    """`SelfPlayEnv.step` takes a flat action string; `_decide_move` returns
    a typed `Action` — this is the one-way translation the parity test needs
    to drive `SelfPlayEnv` from `CopBrain`'s own real decisions."""
    if isinstance(action, Move):
        return action.direction
    assert isinstance(action, PlaceBarrier)
    delta = Position(action.target.col - own_pos.col, action.target.row - own_pos.row)
    for direction, candidate_delta in DELTAS.items():
        if candidate_delta == delta:
            return f"BARRIER_{direction}"
    raise AssertionError(f"barrier target {action.target} is not orthogonally adjacent to {own_pos}")


def test_selfplay_env_matches_run_local_subgame_given_the_same_policy_and_opponent(config):
    movement_only_config = dataclasses.replace(config, barrier_quota=0)
    board = Board(size=movement_only_config.board_size)

    subgame_outcome = run_local_subgame(
        CopBrain(), greedy_thief_move, board, movement_only_config
    )

    rl_config = RLTrainingConfig(
        episode_count=1,
        seed=0,
        curriculum_switch_episode=0,
        curriculum_switch_episode_2=0,
        curriculum_switch_episode_3=0,
        alpha=0.1,
        gamma=0.95,
        epsilon_start=0.0,
        epsilon_end=0.0,
        epsilon_decay=1.0,
        distance_shaping_weight=0.1,
        step_cost=0.01,
        barrier_restriction_bonus_weight=0.0,
        synthetic_thief_lie_probability=0.0,
        belief_expected_distance_shaping_weight=0.0,
        max_refinement_rounds=1,
        win_rate_target=0.0,
        wall_clock_budget_seconds=1.0,
    )
    env = SelfPlayEnv(board, movement_only_config, rl_config, greedy_thief_move, random.Random(0))
    env.reset()
    cop_brain = CopBrain()
    done = False
    env_outcome = None
    while not done:
        direction = cop_brain._pick_move(env.cop_pos, env.thief_pos, board, env._barriers)
        _next_state, _reward, done, env_outcome = env.step(direction)

    assert env_outcome == subgame_outcome


def test_selfplay_env_matches_run_local_subgame_with_real_barriers_enabled(config):
    """PRD 14 sub-layer B: `config`'s real `barrier_quota` (14, not 0) drives
    both sides through `CopBrain._decide_move` (movement *and* its barrier
    heuristic), covering all three capture shapes for the first time in
    `SelfPlayEnv` — coordinate, barrier/rule-46, and imprisonment/rule-47,
    the last only reachable once barriers are real. Guards the exact physics
    gap `env.py`'s own docstring calls out: before this sub-layer, rule 47
    was structurally unreachable in `SelfPlayEnv`."""
    board = Board(size=config.board_size)

    subgame_outcome = run_local_subgame(CopBrain(), greedy_thief_move, board, config)

    rl_config = RLTrainingConfig(
        episode_count=1,
        seed=0,
        curriculum_switch_episode=0,
        curriculum_switch_episode_2=0,
        curriculum_switch_episode_3=0,
        alpha=0.1,
        gamma=0.95,
        epsilon_start=0.0,
        epsilon_end=0.0,
        epsilon_decay=1.0,
        distance_shaping_weight=0.1,
        step_cost=0.01,
        barrier_restriction_bonus_weight=0.0,
        synthetic_thief_lie_probability=0.0,
        belief_expected_distance_shaping_weight=0.0,
        max_refinement_rounds=1,
        win_rate_target=0.0,
        wall_clock_budget_seconds=1.0,
    )
    env = SelfPlayEnv(board, config, rl_config, greedy_thief_move, random.Random(0))
    env.reset()
    cop_brain = CopBrain()
    done = False
    env_outcome = None
    while not done:
        action = cop_brain._decide_move(env.cop_pos, env.thief_pos, board, env._barriers)
        action_string = _action_to_env_string(action, env.cop_pos)
        _next_state, _reward, done, env_outcome = env.step(action_string)

    assert env_outcome == subgame_outcome
