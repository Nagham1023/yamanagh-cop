"""Episode loop: epsilon-greedy tabular Q-learning over `SelfPlayEnv` (PRD 11).

Curriculum: episodes before `curriculum_switch_episode` train against
`make_random_walk_thief` (stage 0, easy), episodes from there to
`curriculum_switch_episode_2` against `greedy_escape_thief` (stage 1,
harder), episodes after that against `lookahead_evader_thief` (PRD 14
stage 2, hardest — depth-2 escape-route lookahead) — early Q-values form
over a low-variance opponent before harder ones are introduced.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from cop.domain.board import Board
from cop.shared.config import GameConfig

from .config import RLTrainingConfig
from .env import SelfPlayEnv
from .opponent_policies import greedy_escape_thief, lookahead_evader_thief, make_random_walk_thief
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
        else:
            opponent = lookahead_evader_thief
        env = SelfPlayEnv(board, game_config, rl_config, opponent)
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
