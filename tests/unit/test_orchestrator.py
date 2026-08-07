"""Orchestrator construction and its client role against a live and a slow
peer (rule 6).

Real HTTP round-trips (via background threads on free ports), not mocks —
same style as test_mcp_client.py. tmp_path keeps every test's trace log out
of the real repo's logs/ directory. Split across three files by concern,
each kept under the 150-line house cap: this one (construction + the happy
path + a slow peer), test_orchestrator_peer_failures.py (a dead port and a
silent peer), and test_orchestrator_watchdog.py (watchdog wiring).
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

import pytest
from fastmcp import FastMCP

from cop.orchestrator import Orchestrator
from cop.planner.deadline import DeadlineExceededError
from cop.reasoning.brain_base import Move
from cop.reasoning.cop_brain import CopBrain


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_constructing_wires_all_five_subsystems(config, tmp_path):
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    assert orchestrator.state_machine.state == "WAITING_FOR_OPPONENT"
    assert orchestrator.server is not None
    assert orchestrator.watchdog is not None
    assert orchestrator.trace is not None
    assert orchestrator.brain is not None


def test_commit_and_reveal_to_peer_round_trips_and_resolves_the_turn(config, tmp_path):
    port = _free_port()
    server = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "server_trace.jsonl"))
    thread = threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    )
    thread.start()
    time.sleep(0.5)

    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.state_machine.transition("COMPUTING_MOVE")  # commit_and_reveal_to_peer owns COMMITTING onward
    result = asyncio.run(
        client.commit_and_reveal_to_peer(
            f"http://127.0.0.1:{port}/mcp", Move(direction="NORTH"), False, "quiet by the river"
        )
    )

    assert result == {"accepted": True, "word_count": 4}
    assert client.state_machine.state == "WAITING_FOR_OPPONENT"
    assert client._pending_nonces  # a nonce was retained for this turn's step


def test_commit_and_reveal_to_peer_deadline_exceeded_transitions_to_technical_loss_and_logs(
    config, tmp_path
):
    # A standalone slow server (not build_server) — deliberately responds
    # slower than the client's timeout, to prove expiry, not connection
    # failure. A refused connection isn't a useful test here: it fails fast
    # with a different exception, never reaching DeadlineExceededError.
    # The first network call in the new flow is receive_commit — sleeping
    # there is enough to trip the client's deadline before Step 1 finishes.
    slow = FastMCP("slow_peer")

    @slow.tool
    def receive_commit(h_commit: str) -> dict:
        time.sleep(0.3)
        return {"acknowledged": True}

    port = _free_port()
    thread = threading.Thread(
        target=slow.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": port, "show_banner": False},
        daemon=True,
    )
    thread.start()
    time.sleep(0.5)

    fast_config = config.__class__(**{**config.__dict__, "response_timeout_seconds": 0.05})
    orchestrator = Orchestrator(fast_config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    orchestrator.state_machine.transition("COMPUTING_MOVE")

    with pytest.raises(DeadlineExceededError):
        asyncio.run(
            orchestrator.commit_and_reveal_to_peer(
                f"http://127.0.0.1:{port}/mcp", Move(direction="NORTH"), False, "a test hint"
            )
        )

    assert orchestrator.state_machine.state == "TECHNICAL_LOSS"

    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "technical_loss" in events
