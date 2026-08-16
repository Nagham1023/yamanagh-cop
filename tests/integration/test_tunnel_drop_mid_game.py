"""Rule 6/7 hardening (PRD 5): a connection that genuinely worked once,
then drops — the shape a real tunnel failure mid-game produces, distinct
from PRD 2's dead-port/killed-peer tests, which never had a live exchange
before the peer disappeared. Needs a real, killable OS process (a
background thread can't be killed), same `_helpers.py` pattern as every
other two-process test in this suite.
"""

from __future__ import annotations

import asyncio
import json
import time

from _helpers import REPO_CONFIG
from _helpers import free_port as _free_port
from _helpers import spawn_server as _spawn_server
from _helpers import wait_for_port as _wait_for_port

from cop.orchestrator import Orchestrator
from cop.reasoning.brain_base import Move
from cop.reasoning.cop_brain import CopBrain
from cop.shared.config import GameConfig
from cop.tools.mcp_client_prd6 import send_reveal
from cop.tools.peer_connection import PeerConnection


def test_a_connection_that_worked_once_then_drops_reaches_technical_loss_cleanly(tmp_path):
    port = _free_port()
    log_path = tmp_path / "peer_trace.jsonl"
    peer = _spawn_server(port, log_path)
    try:
        _wait_for_port(port)

        # First attempt: the connection genuinely works.
        first_result = asyncio.run(
            send_reveal(
                PeerConnection(f"http://127.0.0.1:{port}/mcp"),
                {"type": "move", "direction": "NORTH"},
                "a test hint",
                time.time(),
                time.time() + 30.0,
            )
        )
        assert first_result["accepted"] is True

        # The "tunnel dropped mid-game" shape: kill the peer that just
        # worked, not a peer that was never reachable at all.
        peer.kill()
        peer.wait(timeout=5)

        config = GameConfig.from_file(REPO_CONFIG)
        fast_config = config.__class__(**{**config.__dict__, "response_timeout_seconds": 1.0})
        client = Orchestrator(fast_config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
        client.state_machine.transition("COMPUTING_MOVE")  # commit_and_reveal_to_peer owns COMMITTING onward

        start = time.monotonic()
        try:
            asyncio.run(
                client.commit_and_reveal_to_peer(
                    f"http://127.0.0.1:{port}/mcp", Move(direction="NORTH"), False, "a test hint"
                )
            )
            raised = False
        except Exception:
            raised = True
        elapsed = time.monotonic() - start

        assert raised, "a connection that stops being reachable must not be silently treated as a success"
        assert elapsed < 5.0, "must fail fast, not hang toward the full response_timeout_seconds"
        assert client.state_machine.state == "TECHNICAL_LOSS"

        events = [
            json.loads(line)["event"]
            for line in (tmp_path / "client_trace.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert "technical_loss" in events
    finally:
        peer.terminate()
        peer.wait(timeout=5)
