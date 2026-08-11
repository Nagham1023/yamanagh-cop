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

from greedy_thief_mover import greedy_thief_move

from cop.domain.board import Board
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.subgame import run_local_subgame
from training.config import RLTrainingConfig
from training.env import SelfPlayEnv


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
        alpha=0.1,
        gamma=0.95,
        epsilon_start=0.0,
        epsilon_end=0.0,
        epsilon_decay=1.0,
        distance_shaping_weight=0.1,
        step_cost=0.01,
        max_refinement_rounds=1,
        win_rate_target=0.0,
        wall_clock_budget_seconds=1.0,
    )
    env = SelfPlayEnv(board, movement_only_config, rl_config, greedy_thief_move)
    env.reset()
    cop_brain = CopBrain()
    done = False
    env_outcome = None
    while not done:
        direction = cop_brain._pick_move(env.cop_pos, env.thief_pos, board, env._barriers)
        _next_state, _reward, done, env_outcome = env.step(direction)

    assert env_outcome == subgame_outcome
