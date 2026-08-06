"""Watch PRD 2's milestone run live: two real OS processes round-tripping a
message over localhost, an illegal transition rejected, and a killed peer
producing a clean technical loss with an intact log — not a hang.

Reuses tests/integration/_server_process.py to launch the second peer, the
same way the automated integration test does — one launcher, not two
copies of "how to start a peer server process."

Run:
    uv run python scripts/watch_prd2_roundtrip.py
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

from cop.orchestrator import Orchestrator
from cop.planner.state_machine import PeerStateMachine
from cop.shared.config import GameConfig
from cop.tools.mcp_client import send_position

REPO_ROOT = Path(__file__).resolve().parent.parent
HELPER = REPO_ROOT / "tests" / "integration" / "_server_process.py"
CONFIG_PATH = REPO_ROOT / "config" / "shared" / "config_dev_g01.json"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_port(port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"server on port {port} never came up")


def spawn_peer(port: int, log_path: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable, str(HELPER),
            "--port", str(port),
            "--log-path", str(log_path),
            "--config", str(CONFIG_PATH),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    print("1. Two real OS processes, message round-trip (the milestone)")
    port = free_port()
    log_path = Path("/tmp/watch_prd2_trace.jsonl")
    log_path.unlink(missing_ok=True)
    peer = spawn_peer(port, log_path)

    try:
        wait_for_port(port)
        print(f"  peer B is a separate OS process, pid={peer.pid}, listening on port {port}")
        data = asyncio.run(send_position(f"http://127.0.0.1:{port}/mcp", col=4, row=5))
        print(f"  agent A sends (col=4, row=5) -> agent B decodes: {data}")

        print("\n2. An illegal state transition is rejected, not absorbed (rule 5)")
        machine = PeerStateMachine()
        try:
            machine.transition("TURN_RESOLVED")
        except ValueError as exc:
            print(f"  WAITING_FOR_OPPONENT -> TURN_RESOLVED rejected: {exc}")
        print(f"  state after the rejected attempt: {machine.state} (unchanged)")

        print("\n3. Killing the peer produces a clean technical loss, not a hang (rules 6/7)")
        killed_pid = peer.pid
        peer.kill()
        peer.wait(timeout=5)
        print(f"  peer B (pid={killed_pid}) killed")

        config = GameConfig.from_file(CONFIG_PATH)
        fast_config = config.__class__(**{**config.__dict__, "response_timeout_seconds": 1.0})
        orchestrator = Orchestrator(fast_config, log_path=str(log_path))

        start = time.monotonic()
        try:
            asyncio.run(orchestrator.send_to_peer(f"http://127.0.0.1:{port}/mcp", col=1, row=1))
        except Exception as exc:
            elapsed = time.monotonic() - start
            print(f"  send_to_peer raised {type(exc).__name__} after {elapsed:.2f}s — not a hang")
        print(f"  orchestrator state: {orchestrator.state_machine.state}")

        print("\n4. The technical loss produced a real, readable log entry")
        events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
        technical_loss_events = [e for e in events if e["event"] == "technical_loss"]
        print(f"  {log_path} has {len(events)} entries; last technical_loss entry:")
        print(f"    {technical_loss_events[-1]}")
    finally:
        if peer.poll() is None:
            peer.terminate()
            peer.wait(timeout=5)

    print("\nAll PRD 2 milestone behaviours ran end-to-end.")


if __name__ == "__main__":
    main()
