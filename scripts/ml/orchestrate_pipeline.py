"""`uv run python scripts/ml/orchestrate_pipeline.py`'s real logic lives in
`training/pipeline/` (stages.py, refinement_loop.py, artifacts.py) — this
stays a thin argparse+dispatch wrapper, the same "logic in a plain
function, CLI is just the caller" split `cli_peer.py`/`__main__.py` already
use.

Stages `train`/`evaluate`/`quantize`/`benchmark` run standalone against an
existing `--run-id`'s artifacts; `refine` runs the bounded train/eval
cycle (PLAN.md §6's discipline) and reports its own `--run-id-prefix`.
`all` runs one full train->evaluate->quantize->benchmark pass, no
refinement — for a single deterministic run, not a search. `ensemble`
(PRD 14 round-2 post-gate) trains `--seed-count` independent seeds under
its own `--run-id-prefix`, keeps the top `--keep-count` by belief-aware
win-rate, and merges them into one checkpoint — see
`training/pipeline/ensemble.py`'s own docstring for the selection/merge
policy.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from cop.shared.config import GameConfig  # noqa: E402
from training.config import RLTrainingConfig  # noqa: E402
from training.pipeline import stages  # noqa: E402
from training.pipeline.ensemble import run_ensemble  # noqa: E402
from training.pipeline.refinement_loop import run_train_eval_cycle  # noqa: E402

DEFAULT_GAME_CONFIG = "config/shared/config_dev_g01.json"
DEFAULT_RL_CONFIG = "config/rl_training.toml"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ML training pipeline (PRD 13)")
    parser.add_argument(
        "--stage",
        required=True,
        choices=["train", "evaluate", "quantize", "benchmark", "all", "refine", "ensemble"],
    )
    parser.add_argument("--config", default=DEFAULT_GAME_CONFIG)
    parser.add_argument("--rl-config", default=DEFAULT_RL_CONFIG)
    parser.add_argument("--run-id", help="required for train/evaluate/quantize/benchmark/all")
    parser.add_argument("--run-id-prefix", help="required for --stage refine/ensemble")
    parser.add_argument("--seed-count", type=int, default=20, help="--stage ensemble only")
    parser.add_argument("--keep-count", type=int, default=5, help="--stage ensemble only")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    game_config = GameConfig.from_file(args.config)
    rl_config = RLTrainingConfig.from_toml(args.rl_config)

    if args.stage == "refine":
        if not args.run_id_prefix:
            print("--run-id-prefix is required for --stage refine", file=sys.stderr)
            return 2
        result = run_train_eval_cycle(game_config, rl_config, args.run_id_prefix, args.config)
        print(f"converged={result.converged} rounds_run={result.rounds_run} best_run_id={result.best_run_id}")
        for entry in result.refinement_log:
            print(f"  round {entry['round']}: episode_count={entry['episode_count']} win_rate={entry['win_rate']}")
        return 0 if result.converged else 1

    if args.stage == "ensemble":
        if not args.run_id_prefix:
            print("--run-id-prefix is required for --stage ensemble", file=sys.stderr)
            return 2
        result = run_ensemble(
            game_config, rl_config, args.run_id_prefix, args.config,
            seed_count=args.seed_count, keep_count=args.keep_count,
        )
        print(
            f"ensemble_win_rate_vs_baseline={result['ensemble_win_rate_vs_baseline']} "
            f"ensemble_win_rate_vs_baseline_belief_aware="
            f"{result['ensemble_win_rate_vs_baseline_belief_aware']} "
            f"best_single_seed={result['best_single_seed_win_rate_vs_baseline_belief_aware']}"
        )
        return 0

    if not args.run_id:
        print("--run-id is required for this stage", file=sys.stderr)
        return 2

    if args.stage in ("train", "all"):
        print(stages.run_train(game_config, rl_config, args.run_id, args.config))
    if args.stage in ("evaluate", "all"):
        print(stages.run_evaluate(game_config, args.run_id))
        print(stages.run_evaluate_belief_aware(game_config, rl_config, args.run_id))
    if args.stage in ("quantize", "all"):
        print(stages.run_quantize(args.run_id))
    if args.stage in ("benchmark", "all"):
        print(stages.run_benchmark(game_config, rl_config, args.run_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
