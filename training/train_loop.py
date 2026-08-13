"""Episode loop: epsilon-greedy tabular Q-learning over `SelfPlayEnv` (PRD 11).

Curriculum: episodes before `curriculum_switch_episode` train against
`make_random_walk_thief` (stage 0, easy), episodes from there to
`curriculum_switch_episode_2` against `greedy_escape_thief` (stage 1,
harder), episodes from there to `curriculum_switch_episode_3` against
`lookahead_evader_thief` (PRD 14 stage 2 — depth-2 escape-route lookahead),
episodes after that against a fresh `make_scent_backtracking_thief` (PRD 14
round-2 post-gate, stage 3 — deliberately backtracks into its own scent
trail to stress-test belief-reading, not raw pursuit difficulty) — early
Q-values form over a low-variance opponent before harder ones are
introduced.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from cop.domain.board import Board
from cop.shared.config import GameConfig

from .config import RLTrainingConfig
from .env import SelfPlayEnv
from .opponent_policies import (
    greedy_escape_thief,
    lookahead_evader_thief,
    make_random_walk_thief,
    make_scent_backtracking_thief,
)
from .q_table import QTable


@dataclass(frozen=True)
class TrainMetrics:
    episode_count: int
    final_epsilon: float
    reward_history: tuple[float, ...] = field(default_factory=tuple)


def train(game_config: GameConfig, rl_config: RLTrainingConfig) -> tuple[QTable, TrainMetrics]:
    """Deterministic given `rl_config.seed` — same seed, same trained table
    (see `tests/unit/test_q_table.py`'s determinism test)."""
    rng = random.Random(rl_config.seed)
    # A single stream spanning the whole run, derived from (not the same
    # object as) rng — decouples the belief-simulation coin flips (synthetic
    # hint lie/truth) from opponent-move/epsilon-greedy draws, and must
    # never be reconstructed per-episode (see belief_tracker.py's own
    # docstring for the spurious-artifact risk that would create).
    belief_rng = random.Random(rng.random())
    board = Board(size=game_config.board_size)
    q_table = QTable()
    epsilon = rl_config.epsilon_start
    reward_history: list[float] = []
    random_walk_thief = make_random_walk_thief(rng)

    for episode in range(rl_config.episode_count):
        if episode < rl_config.curriculum_switch_episode:
            opponent = random_walk_thief
        elif episode < rl_config.curriculum_switch_episode_2:
            opponent = greedy_escape_thief
        elif episode < rl_config.curriculum_switch_episode_3:
            opponent = lookahead_evader_thief
        else:
            # Deliberately NOT hoisted outside the loop like the other three
            # stages -- a fresh ScentField every episode is required here
            # (see make_scent_backtracking_thief's own docstring); reusing
            # one across episodes would leak "old trail" across unrelated
            # games. Do not "fix" this back to match the other stages.
            opponent = make_scent_backtracking_thief(game_config, rng)
        env = SelfPlayEnv(board, game_config, rl_config, opponent, belief_rng)
        state = env.reset()
        total_reward = 0.0
        done = False
        while not done:
            legal = env.legal_actions()
            if rng.random() < epsilon:
                action = rng.choice(legal)
            else:
                action = q_table.best_legal_action(state, legal)
            next_state, reward, done, _outcome = env.step(action)
            best_next = 0.0 if done else q_table.best_value(next_state)
            current = q_table.value(state, action)
            updated = current + rl_config.alpha * (reward + rl_config.gamma * best_next - current)
            q_table.update(state, action, updated)
            state = next_state
            total_reward += reward
        reward_history.append(total_reward)
        epsilon = max(rl_config.epsilon_end, epsilon * rl_config.epsilon_decay)

    metrics = TrainMetrics(
        episode_count=rl_config.episode_count,
        final_epsilon=epsilon,
        reward_history=tuple(reward_history),
    )
    return q_table, metrics
