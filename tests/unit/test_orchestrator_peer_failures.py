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
from fastmcp import FastMCP

from cop.orchestrator import Orchestrator
from cop.planner.deadline import DeadlineExceededError
from cop.reasoning.brain_base import Move
from cop.reasoning.cop_brain import CopBrain


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_commit_and_reveal_to_peer_against_a_dead_port_reaches_technical_loss_without_hanging(
    config, tmp_path
):
    # Found while writing the two-process integration test: a killed peer's
    # port closes immediately (connection refused), which is NOT a timeout —
    # asyncio.wait_for lets that exception through unchanged. The original
    # `except DeadlineExceededError` would have missed this entirely, leaving
    # the state machine stuck in AWAITING_REVEAL and nothing logged.
    port = _free_port()  # never bound to any server — guaranteed refused
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    orchestrator.state_machine.transition("COMPUTING_MOVE")  # commit_and_reveal_to_peer owns COMMITTING onward

    start = time.monotonic()
    with pytest.raises(Exception):  # noqa: B017 - deliberately broad: any connection failure counts
        asyncio.run(
            orchestrator.commit_and_reveal_to_peer(
                f"http://127.0.0.1:{port}/mcp", Move(direction="NORTH"), False, "a test hint"
            )
        )
    elapsed = time.monotonic() - start

    assert elapsed < 5.0, "must fail fast, not hang toward the full response_timeout_seconds"
    assert orchestrator.state_machine.state == "TECHNICAL_LOSS"

    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "technical_loss" in events


def test_commit_and_reveal_to_peer_against_a_silent_peer_hits_the_deadline_not_a_socket_error(
    config, tmp_path
):
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
    orchestrator = Orchestrator(fast_config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    orchestrator.state_machine.transition("COMPUTING_MOVE")

    start = time.monotonic()
    try:
        with pytest.raises(DeadlineExceededError):
            asyncio.run(
                orchestrator.commit_and_reveal_to_peer(
                    f"http://127.0.0.1:{port}/mcp", Move(direction="NORTH"), False, "a test hint"
                )
            )
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


def test_commit_and_reveal_to_peer_retries_past_a_momentary_connection_refusal(config, tmp_path):
    # The exact real-match failure this closes: a second successful
    # 27-round match still forfeited because send_commit hit a bare
    # ConnectError on an already-open PeerConnection (round 27's own
    # reconnect attempt failing, not the first handshake) and had zero
    # retry. Nothing is bound to `port` yet, so the first attempt gets a
    # real connection-refused; the real FastMCP server only starts
    # listening after a short beat, simulating the tunnel coming back.
    port = _free_port()
    recovering = FastMCP("recovering_commit_peer")

    @recovering.tool
    def receive_commit(h_commit: str, sent_at: float, deadline_at: float) -> dict:
        return {"acknowledged": True}

    @recovering.tool
    def receive_reveal(move: dict, hint_text: str, sent_at: float, deadline_at: float) -> dict:
        return {"accepted": True, "word_count": len(hint_text.split())}

    def _start_late() -> None:
        time.sleep(0.1)
        recovering.run(transport="http", host="127.0.0.1", port=port, show_banner=False)

    threading.Thread(target=_start_late, daemon=True).start()

    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    orchestrator.state_machine.transition("COMPUTING_MOVE")

    asyncio.run(
        orchestrator.commit_and_reveal_to_peer(
            f"http://127.0.0.1:{port}/mcp", Move(direction="NORTH"), False, "a test hint"
        )
    )

    assert orchestrator.state_machine.state == "WAITING_FOR_OPPONENT", (
        "a momentary connection refusal that clears on retry must not force a technical loss"
    )
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "commit_reveal_send_retrying" in events
    assert "technical_loss" not in events


def test_request_scent_map_from_peer_retries_past_a_momentary_connection_refusal(config, tmp_path):
    # The real bug this guards: a free-tier ngrok tunnel dropped for well
    # under a second during a real cross-machine match — the peer's own
    # next call reached us again before we'd even finished failing here —
    # yet the old one-shot call turned that sub-second blip into an
    # instant forfeit. Nothing is bound to `port` yet, so the first attempt
    # gets a real connection-refused; the real FastMCP server only starts
    # listening on that same port after a short beat, simulating the
    # tunnel coming back.
    port = _free_port()
    recovering = FastMCP("recovering_scent_peer")

    @recovering.tool
    def share_scent_map() -> dict:
        return {"cells": {}}

    def _start_late() -> None:
        time.sleep(0.1)
        recovering.run(transport="http", host="127.0.0.1", port=port, show_banner=False)

    threading.Thread(target=_start_late, daemon=True).start()

    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))

    result = asyncio.run(orchestrator.request_scent_map_from_peer(f"http://127.0.0.1:{port}/mcp"))

    assert result == {}
    assert orchestrator.state_machine.state == "WAITING_FOR_OPPONENT", (
        "a momentary connection refusal that clears on retry must not force a technical loss"
    )
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "scent_map_request_retrying" in events
    assert "technical_loss" not in events


def test_request_scent_map_from_peer_against_a_dead_port_still_reaches_technical_loss_after_retries_are_exhausted(
    config, tmp_path
):
    # A genuinely dead peer (nothing ever listening) must still forfeit —
    # the retry only buys tolerance for a momentary blip, not infinite
    # patience, and it must still fail fast, not hang.
    port = _free_port()  # never bound to any server
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    # request_scent_map_from_peer's own docstring: take_turn transitions to
    # COMPUTING_MOVE before calling this specifically so the failure path
    # below has a legal TECHNICAL_LOSS edge — WAITING_FOR_OPPONENT (the
    # default state) does not.
    orchestrator.state_machine.transition("COMPUTING_MOVE")

    start = time.monotonic()
    with pytest.raises(Exception):  # noqa: B017 - deliberately broad: any connection failure counts
        asyncio.run(orchestrator.request_scent_map_from_peer(f"http://127.0.0.1:{port}/mcp"))
    elapsed = time.monotonic() - start

    assert elapsed < 5.0, "must fail fast, not hang toward the full response_timeout_seconds"
    assert orchestrator.state_machine.state == "TECHNICAL_LOSS"
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "technical_loss" in events
    assert events.count("scent_map_request_retrying") == orchestrator.private_config.scent_map_retry_attempts - 1


def test_send_final_reveal_to_peer_retries_past_a_momentary_connection_refusal(config, tmp_path):
    # Same real bug, second call site: receive_final_reveal is a pure
    # overwrite (PeerTrace.record_final_reveal's own setdefault), so a
    # duplicate delivery after a dropped tunnel is a safe no-op on the
    # receiving side.
    port = _free_port()
    recovering = FastMCP("recovering_final_reveal_peer")

    @recovering.tool
    def receive_final_reveal(nonces: dict, intents: dict) -> dict:
        return {"passed": True, "verified_steps": 0, "failed_steps": [], "evaluated": True}

    def _start_late() -> None:
        time.sleep(0.1)
        recovering.run(transport="http", host="127.0.0.1", port=port, show_banner=False)

    threading.Thread(target=_start_late, daemon=True).start()

    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))

    result = asyncio.run(orchestrator.send_final_reveal_to_peer(f"http://127.0.0.1:{port}/mcp"))

    assert result["passed"] is True
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "final_reveal_send_retrying" in events
    assert "final_reveal_failed" not in events


def test_send_final_reveal_to_peer_against_a_dead_port_still_fails_after_retries_are_exhausted(
    config, tmp_path
):
    port = _free_port()  # never bound to any server
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))

    start = time.monotonic()
    with pytest.raises(Exception):  # noqa: B017 - deliberately broad: any connection failure counts
        asyncio.run(orchestrator.send_final_reveal_to_peer(f"http://127.0.0.1:{port}/mcp"))
    elapsed = time.monotonic() - start

    assert elapsed < 10.0, "must fail fast, not hang toward the full response_timeout_seconds"
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "final_reveal_failed" in events
    assert events.count("final_reveal_send_retrying") == orchestrator.private_config.scent_map_retry_attempts - 1


def test_request_scent_map_from_peer_against_a_malformed_response_degrades_gracefully_not_a_technical_loss(
    config, tmp_path
):
    # rule-auditor finding (rule 9 — everything a peer sends is untrusted):
    # a malformed share_scent_map response must not become OUR OWN
    # technical loss on an otherwise-healthy connection — that would let a
    # hostile or buggy peer force our forfeit just by returning garbage.
    malformed = FastMCP("malformed_scent_peer")

    @malformed.tool
    def share_scent_map() -> dict:
        return {"not_cells": "garbage"}  # missing the mandatory "cells" key

    port = _free_port()
    threading.Thread(
        target=malformed.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": port, "show_banner": False},
        daemon=True,
    ).start()
    time.sleep(0.5)

    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))

    result = asyncio.run(orchestrator.request_scent_map_from_peer(f"http://127.0.0.1:{port}/mcp"))

    assert result == {}
    assert orchestrator.state_machine.state == "WAITING_FOR_OPPONENT", (
        "a malformed payload on an otherwise-working connection must not force a technical loss"
    )
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "scent_map_malformed" in events
    assert "technical_loss" not in events
