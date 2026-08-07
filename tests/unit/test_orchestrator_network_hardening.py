"""Rule 6 hardening under realistic latency (PRD 5) — no new production
mechanism, new verification. The deadline tracker was already built in
PRD 2; this proves it doesn't falsely trip under a modest, realistic
delay. The companion "connection worked once, then dropped" case needs a
genuinely killable OS process (a background thread can't be killed) — see
`tests/integration/test_tunnel_drop_mid_game.py`.
"""

from __future__ import annotations

import asyncio
import threading
import time

from fastmcp import FastMCP

from cop.orchestrator import Orchestrator
from cop.reasoning.brain_base import Move
from cop.reasoning.cop_brain import CopBrain


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_commit_and_reveal_to_peer_tolerates_realistic_latency_within_the_deadline(config, tmp_path):
    # A modest, realistic delay (2s) against the *default* response_timeout_seconds
    # (30s, not an artificially shortened one) — contrast with
    # test_orchestrator.py's slow-peer test, which deliberately shortens the
    # deadline to force a timeout. This one must NOT time out.
    slow = FastMCP("realistic_latency_peer")

    @slow.tool
    def receive_commit(h_commit: str) -> dict:
        return {"acknowledged": True}

    @slow.tool
    def receive_reveal(move: dict, hint_text: str) -> dict:
        time.sleep(2.0)
        return {"accepted": True, "word_count": len(hint_text.split())}

    port = _free_port()
    threading.Thread(
        target=slow.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": port, "show_banner": False},
        daemon=True,
    ).start()
    time.sleep(0.5)

    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    orchestrator.state_machine.transition("COMPUTING_MOVE")

    result = asyncio.run(
        orchestrator.commit_and_reveal_to_peer(
            f"http://127.0.0.1:{port}/mcp", Move(direction="NORTH"), False, "a test hint"
        )
    )

    assert result["accepted"] is True
    assert orchestrator.state_machine.state == "WAITING_FOR_OPPONENT"
