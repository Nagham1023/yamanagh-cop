"""Standalone launcher for the two-process integration test.

Runs a real `Orchestrator` server in its own OS process, not a thread — the
whole point of this helper is to be run via `subprocess.Popen`, one per
test-spawned peer, so rule 1 (two completely separate processes) is
actually exercised rather than approximated with threads.
"""

from __future__ import annotations

import argparse
import os

from cop.orchestrator import Orchestrator
from cop.shared.config import GameConfig


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--log-path", required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config = GameConfig.from_file(args.config)
    orchestrator = Orchestrator(config, log_path=args.log_path)
    orchestrator.trace.log("process_started", pid=os.getpid(), port=args.port)
    orchestrator.run_as_server(host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
