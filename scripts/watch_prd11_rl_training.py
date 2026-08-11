"""Watch PRD 11's milestone live: train a tabular Q-learning policy offline,
save a checkpoint, load it into a fresh `RLCopBrain`, and compare its
capture rate against a random-move baseline cop over the same set of
seeded thief opponents — no network, no `Orchestrator`, purely
`reasoning/`+`domain/`+`training/`.

Run:
    uv run python scripts/watch_prd11_rl_training.py
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from cop.domain.barriers import BarrierSet  # noqa: E402
from cop.domain.board import Board, Position  # noqa: E402
from cop.domain.movement import apply_move  # noqa: E402
from cop.domain.scoring import Outcome  # noqa: E402
from cop.reasoning.brain_base import BrainBase  # noqa: E402
from cop.reasoning.rl_cop_brain import RLCopBrain  # noqa: E402
from cop.reasoning.subgame import run_local_subgame  # noqa: E402
from cop.shared.config import GameConfig  # noqa: E402
from training.checkpoint_io import save  # noqa: E402
from training.config import RLTrainingConfig  # noqa: E402
from training.opponent_policies import make_random_walk_thief  # noqa: E402
from training.train_loop import train  # noqa: E402

_CHECKPOINT_PATH = Path("/tmp/watch_prd11_qtable.json")
_EVAL_EPISODES = 20
_EVAL_SEED = 20260812


class _RandomBaselineBrain(BrainBase):
    """Demo-only comparison point — a cop that moves randomly among legal
    directions, never a promoted or shipped strategy."""

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng

    def _pick_move(self, own_pos: Position, target_pos: Position, board: Board, barriers: BarrierSet) -> str:
        legal = ["STAY"]
        for direction in ("N", "E", "S", "W"):
            if apply_move(own_pos, direction, board) is not None:
                legal.append(direction)
        return self._rng.choice(legal)


def _capture_rate(cop_brain_factory, board: Board, config: GameConfig) -> float:
    rng = random.Random(_EVAL_SEED)
    captures = 0
    for _ in range(_EVAL_EPISODES):
        thief_mover = make_random_walk_thief(random.Random(rng.random()))
        outcome = run_local_subgame(cop_brain_factory(), thief_mover, board, config)
        if outcome is Outcome.CAPTURE:
            captures += 1
    return captures / _EVAL_EPISODES


def section_1_train(config: GameConfig, rl_config: RLTrainingConfig):
    print("1. Offline training — no network, no Orchestrator")
    t0 = time.time()
    q_table, metrics = train(config, rl_config)
    elapsed = time.time() - t0
    print(
        f"  trained {metrics.episode_count} episodes in {elapsed:.2f}s, "
        f"{len(q_table.as_dict())} states visited, final epsilon={metrics.final_epsilon:.3f}"
    )
    early_avg = sum(metrics.reward_history[:50]) / 50
    late_avg = sum(metrics.reward_history[-50:]) / 50
    print(f"  reward trend: first 50 episodes avg={early_avg:.2f}, last 50 avg={late_avg:.2f}")
    save(_CHECKPOINT_PATH, q_table)
    print(f"  checkpoint saved to {_CHECKPOINT_PATH}")


def section_2_evaluate(config: GameConfig):
    print(f"\n2. Evaluation — {_EVAL_EPISODES} seeded episodes vs. a random-walk thief")
    board = Board(size=config.board_size)

    rl_rate = _capture_rate(lambda: RLCopBrain(checkpoint_path=_CHECKPOINT_PATH), board, config)
    print(f"  RLCopBrain capture rate:            {rl_rate:.0%}")

    baseline_rate = _capture_rate(
        lambda: _RandomBaselineBrain(random.Random(_EVAL_SEED)), board, config
    )
    print(f"  random-move baseline capture rate:  {baseline_rate:.0%}")

    assert rl_rate >= baseline_rate, "RL brain did not beat the random baseline — investigate before trusting this checkpoint"
    print("  RLCopBrain's capture rate is at least the random baseline's — milestone holds.")


def main() -> None:
    config = GameConfig.from_file("config/shared/config_dev_g01.json")
    rl_config = RLTrainingConfig.from_toml("config/rl_training.toml")
    section_1_train(config, rl_config)
    section_2_evaluate(config)
    print("\nAll PRD 11 milestone behaviours ran end-to-end.")


if __name__ == "__main__":
    main()
