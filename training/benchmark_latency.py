"""_pick_move latency benchmark (PRD 12): realistic states, not just
synthetic edge cases — sampled from real `SelfPlayEnv` episode traces
(random-policy rollouts, so a wide spread of positions/barrier states is
covered) rather than hand-picked corners.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.reasoning.brain_base import BrainBase
from cop.shared.config import GameConfig

from .config import RLTrainingConfig
from .env import SelfPlayEnv
from .opponent_policies import ThiefMover

RealisticState = tuple[Position, Position, Board, BarrierSet]


@dataclass(frozen=True)
class LatencyMetrics:
    """`_pick_move` timing percentiles over a sample of realistic states,
    plus how many samples they're drawn from."""

    p50_seconds: float
    p95_seconds: float
    p99_seconds: float
    sample_count: int


def sample_realistic_states(
    board: Board,
    game_config: GameConfig,
    rl_config: RLTrainingConfig,
    opponent: ThiefMover,
    sample_count: int,
    seed: int,
) -> list[RealisticState]:
    """Drives `SelfPlayEnv` with random legal moves (not a fixed policy) so
    the sampled positions/barrier-adjacency states cover a realistic
    spread, not just whatever one deterministic trajectory visits."""
    rng = random.Random(seed)
    belief_rng = random.Random(rng.random())
    env = SelfPlayEnv(board, game_config, rl_config, opponent, belief_rng)
    samples: list[RealisticState] = []
    while len(samples) < sample_count:
        env.reset()
        done = False
        while not done and len(samples) < sample_count:
            samples.append((env.cop_pos, env.thief_pos, board, env._barriers))
            action = rng.choice(env.legal_actions())
            _next_state, _reward, done, _outcome = env.step(action)
    return samples


def _percentile(sorted_seconds: list[float], fraction: float) -> float:
    """Nearest-rank percentile over an already-sorted sample; `0.0` on an
    empty sample rather than raising, so a zero-sample benchmark still
    returns a well-formed (if meaningless) `LatencyMetrics`."""
    if not sorted_seconds:
        return 0.0
    index = min(len(sorted_seconds) - 1, int(fraction * len(sorted_seconds)))
    return sorted_seconds[index]


def benchmark_pick_move_latency(brain: BrainBase, samples: list[RealisticState]) -> LatencyMetrics:
    """Times `brain._pick_move` directly — the one call every real turn
    makes — over the given samples, using `time.perf_counter` (monotonic,
    sub-microsecond resolution)."""
    timings: list[float] = []
    for own_pos, target_pos, board, barriers in samples:
        start = time.perf_counter()
        brain._pick_move(own_pos, target_pos, board, barriers)
        timings.append(time.perf_counter() - start)
    timings.sort()
    return LatencyMetrics(
        p50_seconds=_percentile(timings, 0.50),
        p95_seconds=_percentile(timings, 0.95),
        p99_seconds=_percentile(timings, 0.99),
        sample_count=len(samples),
    )
