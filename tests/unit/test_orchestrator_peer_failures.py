"""Orchestrator client role against a dead port and a silent peer — split
out of test_orchestrator.py, which grew past the 150-line house cap.

Two distinct, deliberately different failure shapes: a dead port fails
immediately with a socket-level error (connection refused); a silent peer
accepts the connection and then produces no error at all, so only the
deadline tracker can end it.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

import pytest

from cop.orchestrator import Orchestrator
from cop.planner.deadline import DeadlineExceededError


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_send_to_peer_against_a_dead_port_reaches_technical_loss_without_hanging(config, tmp_path):
    # Found while writing the two-process integration test: a killed peer's
    # port closes immediately (connection refused), which is NOT a timeout —
    # asyncio.wait_for lets that exception through unchanged. The original
    # `except DeadlineExceededError` would have missed this entirely, leaving
    # the state machine stuck in AWAITING_RESPONSE and nothing logged.
    port = _free_port()  # never bound to any server — guaranteed refused
    orchestrator = Orchestrator(config, log_path=str(tmp_path / "trace.jsonl"))

    start = time.monotonic()
    with pytest.raises(Exception):  # noqa: B017 - deliberately broad: any connection failure counts
        asyncio.run(orchestrator.send_to_peer(f"http://127.0.0.1:{port}/mcp", col=1, row=1))
    elapsed = time.monotonic() - start

    assert elapsed < 5.0, "must fail fast, not hang toward the full response_timeout_seconds"
    assert orchestrator.state_machine.state == "TECHNICAL_LOSS"

    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "technical_loss" in events


def test_send_to_peer_against_a_silent_peer_hits_the_deadline_not_a_socket_error(config, tmp_path):
    # A peer that accepts the TCP connection and then does nothing at all —
    # no response, no close, no reset. A raw socket held open (not a FastMCP
    # server) is the only way to produce this deterministically: it can't be
    # a connection-refused (the dead-port test above) or a late-but-real
    # response — only the deadline tracker can end this, since no
    # socket-level error ever arrives to catch.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    held_connections: list[socket.socket] = []

    def _accept_and_stay_silent() -> None:
        conn, _ = listener.accept()
        held_connections.append(conn)  # never read, never write, never close

    threading.Thread(target=_accept_and_stay_silent, daemon=True).start()

    fast_config = config.__class__(**{**config.__dict__, "response_timeout_seconds": 0.2})
    orchestrator = Orchestrator(fast_config, log_path=str(tmp_path / "trace.jsonl"))

    start = time.monotonic()
    try:
        with pytest.raises(DeadlineExceededError):
            asyncio.run(orchestrator.send_to_peer(f"http://127.0.0.1:{port}/mcp", col=1, row=1))
        elapsed = time.monotonic() - start

        assert elapsed < 2.0, "silence must be caught by the deadline, not hang indefinitely"
        assert orchestrator.state_machine.state == "TECHNICAL_LOSS"

        events = [
            json.loads(line)["event"]
            for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert "technical_loss" in events
    finally:
        listener.close()
        for conn in held_connections:
            conn.close()
