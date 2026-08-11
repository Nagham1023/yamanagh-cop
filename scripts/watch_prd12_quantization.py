"""Watch PRD 12's milestone live: train a fresh checkpoint (same as PRD 11),
quantize it, and report three real, measured numbers — file-size delta,
argmax-agreement rate, and `_pick_move` p50/p95/p99 latency against
`response_timeout_seconds` — no deployment, no `Orchestrator`.

Run:
    uv run python scripts/watch_prd12_quantization.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from cop.domain.board import Board  # noqa: E402
from cop.reasoning.rl_cop_brain import RLCopBrain  # noqa: E402
from cop.shared.config import GameConfig  # noqa: E402
from training.benchmark_latency import (  # noqa: E402
    benchmark_pick_move_latency,
    sample_realistic_states,
)
from training.checkpoint_io import save, save_quantized  # noqa: E402
from training.config import RLTrainingConfig  # noqa: E402
from training.opponent_policies import greedy_escape_thief  # noqa: E402
from training.quantize import argmax_agreement_rate, quantize_q_table  # noqa: E402
from training.train_loop import train  # noqa: E402

_UNQUANTIZED_PATH = Path("/tmp/watch_prd12_qtable_float.json")
_QUANTIZED_PATH = Path("/tmp/watch_prd12_qtable_int8.json")
_LATENCY_SAMPLE_COUNT = 5000


def section_1_train_and_quantize(config: GameConfig, rl_config: RLTrainingConfig):
    """Trains a fresh checkpoint, saves both a float and a quantized copy,
    and prints the size delta plus the argmax-agreement rate — returns the
    trained `QTable` so section 2 can benchmark against the same run."""
    print("1. Train, then quantize the same checkpoint")
    q_table, metrics = train(config, rl_config)
    print(f"  trained {metrics.episode_count} episodes, {len(q_table.as_dict())} states visited")

    save(_UNQUANTIZED_PATH, q_table)
    save_quantized(_QUANTIZED_PATH, q_table)

    float_size = _UNQUANTIZED_PATH.stat().st_size
    quantized_size = _QUANTIZED_PATH.stat().st_size
    print(f"  float checkpoint:     {float_size} bytes  ({_UNQUANTIZED_PATH})")
    print(f"  quantized checkpoint: {quantized_size} bytes  ({_QUANTIZED_PATH})")
    print(f"  size reduction: {(1 - quantized_size / float_size):.0%}")

    quantized, params = quantize_q_table(q_table.as_dict())
    rate = argmax_agreement_rate(q_table.as_dict(), quantized, params)
    print(f"  argmax-agreement rate (quantized vs. original ranking): {rate:.2%}")
    return q_table


def section_2_latency(config: GameConfig, rl_config: RLTrainingConfig):
    """Benchmarks the quantized checkpoint's `_pick_move` latency over
    realistic sampled states and asserts it fits inside the real turn
    budget — a failed assertion here means the milestone doesn't hold,
    not just a low printed number a human might not check."""
    print(f"\n2. Latency — {_LATENCY_SAMPLE_COUNT} realistic states, quantized checkpoint")
    board = Board(size=config.board_size)
    samples = sample_realistic_states(
        board, config, rl_config, greedy_escape_thief, _LATENCY_SAMPLE_COUNT, seed=20260812
    )
    brain = RLCopBrain(checkpoint_path=_QUANTIZED_PATH)
    result = benchmark_pick_move_latency(brain, samples)

    print(f"  p50: {result.p50_seconds * 1e6:.1f} us")
    print(f"  p95: {result.p95_seconds * 1e6:.1f} us")
    print(f"  p99: {result.p99_seconds * 1e6:.1f} us")

    budget = config.response_timeout_seconds
    if result.p99_seconds > 0:
        margin = budget / result.p99_seconds
        print(f"  response_timeout_seconds budget: {budget}s — p99 is {margin:,.0f}x under budget")
    assert result.p99_seconds < budget, "p99 latency exceeds the real turn budget — investigate"
    print("  p99 latency comfortably fits inside the real turn budget — milestone holds.")


def main() -> None:
    """Runs both milestone sections in order against the real repo config."""
    config = GameConfig.from_file("config/shared/config_dev_g01.json")
    rl_config = RLTrainingConfig.from_toml("config/rl_training.toml")
    section_1_train_and_quantize(config, rl_config)
    section_2_latency(config, rl_config)
    print("\nAll PRD 12 milestone behaviours ran end-to-end.")


if __name__ == "__main__":
    main()
