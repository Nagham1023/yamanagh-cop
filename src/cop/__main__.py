"""CLI entry point — `uv run python -m cop peer` / `... replay --log <path>`
(`CLAUDE.md`/`README.md`'s own documented commands, unbuilt since PRD 6
first flagged the gap and PRD 7 explicitly deferred it). Stays a thin
`argparse` + dispatch wrapper; real logic lives in `cli_peer.py`/
`cli_replay.py`, both independently testable without going through argv.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .cli_peer import DEFAULT_PRIVATE_CONFIG_PATH, DEFAULT_SHARED_CONFIG_PATH, run_peer
from .cli_replay import run_replay
from .orchestrator_step0 import Step0MismatchError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cop")
    subparsers = parser.add_subparsers(dest="command", required=True)

    peer_parser = subparsers.add_parser(
        "peer", help="run this peer against config/game.toml's own [network].opponent_url"
    )
    peer_parser.add_argument(
        "--counted", action="store_true",
        help="count this match toward rule 31/52 (default: an uncounted warm-up)",
    )
    peer_parser.add_argument(
        "--tunnel", action="store_true",
        help="expose this peer via ngrok (rule 10) — needed for a real cross-machine match",
    )
    peer_parser.add_argument(
        "--gui", action="store_true",
        help="open live belief heatmap GUI window during the match",
    )
    peer_parser.add_argument("--private-config", default=DEFAULT_PRIVATE_CONFIG_PATH)
    peer_parser.add_argument("--shared-config", default=DEFAULT_SHARED_CONFIG_PATH)

    replay_parser = subparsers.add_parser("replay", help="verify a recorded match's log file")
    replay_parser.add_argument("--log", required=True, help="path to log_<game_id>_g<NN>.json")
    replay_parser.add_argument(
        "--gui", action="store_true", help="also open a real Tkinter replay window"
    )

    return parser


def main() -> None:
    args = _build_parser().parse_args()

    if args.command == "peer":
        try:
            asyncio.run(
                run_peer(
                    args.private_config,
                    args.shared_config,
                    counted=args.counted,
                    use_tunnel=args.tunnel,
                    gui=args.gui,
                )
            )
        except Step0MismatchError as exc:
            print(f"Step-0 negotiation failed: {exc}", file=sys.stderr)
            sys.exit(1)
        except ValueError as exc:
            # rule-auditor's own finding: a real rule-52 violation
            # (--counted against an opponent already counted,
            # league_ledger.py's own ValueError) reached here as a raw
            # traceback — same clean exit as a Step0MismatchError now.
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "replay":
        sys.exit(run_replay(args.log, gui=args.gui))


if __name__ == "__main__":
    main()
