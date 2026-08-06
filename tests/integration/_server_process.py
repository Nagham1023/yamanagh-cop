"""Standalone launcher for the two-process integration tests.

Runs a real `Orchestrator` server in its own OS process, not a thread — the
whole point of this helper is to be run via `subprocess.Popen`, one per
test-spawned peer, so rule 1 (two completely separate processes) is
actually exercised rather than approximated with threads.

`--peer-port` is optional: when given, this process also acts as a client
once both its own server and the peer's are reachable, sending
`--peer-text`. That's what lets the concurrent-exchange test have a real OS
process send and receive within the same run, not just receive.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import threading

from _helpers import wait_for_port

from cop.orchestrator import Orchestrator
from cop.reasoning.cop_brain import CopBrain
from cop.shared.config import GameConfig


def _send_once_peer_is_up(orchestrator: Orchestrator, peer_port: int, text: str, scent_report: str) -> None:
    wait_for_port(peer_port)
    orchestrator.state_machine.transition("COMPUTING_MOVE")  # send_to_peer only owns SENDING onward
    asyncio.run(orchestrator.send_to_peer(f"http://127.0.0.1:{peer_port}/mcp", text, scent_report))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--log-path", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--peer-port", type=int, default=None)
    parser.add_argument("--peer-text", default="a test hint")
    parser.add_argument("--peer-scent-report", default="Scent strongest to the north west.")
    args = parser.parse_args()

    config = GameConfig.from_file(args.config)
    orchestrator = Orchestrator(config, CopBrain(), log_path=args.log_path)
    orchestrator.trace.log("process_started", pid=os.getpid(), port=args.port)

    if args.peer_port is not None:
        threading.Thread(
            target=_send_once_peer_is_up,
            args=(orchestrator, args.peer_port, args.peer_text, args.peer_scent_report),
            daemon=True,
        ).start()

    orchestrator.run_as_server(host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
