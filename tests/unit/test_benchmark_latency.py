"""benchmark_latency: sampling produces realistic states, the benchmark
itself runs and produces well-formed, sane metrics."""

from __future__ import annotations

from cop.domain.board import Board
from cop.reasoning.cop_brain import CopBrain
from training.benchmark_latency import benchmark_pick_move_latency, sample_realistic_states
from training.config import RLTrainingConfig
from training.opponent_policies import greedy_escape_thief

_RL_CONFIG = RLTrainingConfig(
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


def test_sample_realistic_states_returns_exactly_the_requested_count(config):
    board = Board(size=config.board_size)
    samples = sample_realistic_states(board, config, _RL_CONFIG, greedy_escape_thief, 50, seed=1)
    assert len(samples) == 50


def test_sample_realistic_states_is_deterministic_for_a_fixed_seed(config):
    board = Board(size=config.board_size)
    first = sample_realistic_states(board, config, _RL_CONFIG, greedy_escape_thief, 30, seed=7)
    second = sample_realistic_states(board, config, _RL_CONFIG, greedy_escape_thief, 30, seed=7)
    assert first == second


def test_benchmark_produces_ordered_nonnegative_percentiles(config):
    board = Board(size=config.board_size)
    samples = sample_realistic_states(board, config, _RL_CONFIG, greedy_escape_thief, 200, seed=1)
    metrics = benchmark_pick_move_latency(CopBrain(), samples)
    assert metrics.sample_count == 200
    assert 0.0 <= metrics.p50_seconds <= metrics.p95_seconds <= metrics.p99_seconds


def test_benchmark_on_zero_samples_returns_zeroed_metrics_not_a_crash(config):
    metrics = benchmark_pick_move_latency(CopBrain(), [])
    assert metrics.sample_count == 0
    assert metrics.p50_seconds == metrics.p95_seconds == metrics.p99_seconds == 0.0
