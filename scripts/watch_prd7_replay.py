"""Watch PRD 7's Replay Viewer milestone run live: a real committed-and-
revealed exchange, opened in the Replay Viewer, showing `Verified OK` —
then the same log tampered, showing `TAMPERED` — the "second, adversarial
milestone" `PRD-7-reporting-shell.md`'s own Milestone section requires,
demonstrated live, not just tested.

Run:
    uv run python scripts/watch_prd7_replay.py
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from pathlib import Path

from cop.observability.replay_viewer import ReplayViewer, ReplayViewerWindow
from cop.orchestrator import Orchestrator
from cop.reasoning.brain_base import Move
from cop.reasoning.cop_brain import CopBrain
from cop.shared.config import GameConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "shared" / "config_dev_g01.json"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> None:
    config = GameConfig.from_file(CONFIG_PATH)
    log_path = Path("/tmp/watch_prd7_replay_trace.jsonl")
    log_path.unlink(missing_ok=True)

    print("1. A real committed-and-revealed exchange")
    port = _free_port()
    server = Orchestrator(config, CopBrain(), log_path=str(log_path.with_suffix(".server.jsonl")))
    threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    client = Orchestrator(config, CopBrain(), log_path=str(log_path))
    client.state_machine.transition("COMPUTING_MOVE")
    result = asyncio.run(
        client.commit_and_reveal_to_peer(
            f"http://127.0.0.1:{port}/mcp", Move(direction="N"), False, "quiet by the river"
        )
    )
    print(f"  reveal ack: {result}")

    print("\n2. Opening it in the Replay Viewer — honest path")
    honest_viewer = ReplayViewer(log_path, client._pending_nonces)
    print(f"  overall status: {honest_viewer.overall_status}")
    assert honest_viewer.overall_status == "Verified OK"
    honest_window = ReplayViewerWindow(honest_viewer)
    print(f"  window banner: {honest_window.banner.cget('text')!r} (fg={honest_window.banner.cget('fg')})")
    honest_window.close()

    print("\n3. The adversarial case: tamper the log, reopen it")
    lines = log_path.read_text(encoding="utf-8").splitlines()
    tampered_lines = []
    for line in lines:
        entry = json.loads(line)
        if entry["event"] == "committing":
            entry["move"] = {"type": "move", "direction": "S"}  # tampered after the fact
        tampered_lines.append(json.dumps(entry))
    tampered_log = log_path.with_suffix(".tampered.jsonl")
    tampered_log.write_text("\n".join(tampered_lines) + "\n", encoding="utf-8")

    tampered_viewer = ReplayViewer(tampered_log, client._pending_nonces)
    print(f"  overall status: {tampered_viewer.overall_status} (must be TAMPERED)")
    assert tampered_viewer.overall_status == "TAMPERED"
    tampered_window = ReplayViewerWindow(tampered_viewer)
    print(f"  window banner: {tampered_window.banner.cget('text')!r} (fg={tampered_window.banner.cget('fg')})")
    tampered_window.close()

    print("\nAll PRD 7 Replay Viewer milestone behaviours ran end-to-end, including the adversarial case.")


if __name__ == "__main__":
    main()
