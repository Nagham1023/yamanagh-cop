"""Coverage for `commit_and_reveal_to_peer`'s two defensive branches not
exercised by the happy-path tests in `test_orchestrator.py`: the local
self-check failing (a genuine local bug, not opponent dishonesty) and the
barrier-declaration call itself failing.
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
from cop.reasoning.brain_base import Move, PlaceBarrier
from cop.reasoning.cop_brain import CopBrain


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_commit_and_reveal_only_server() -> int:
    """A peer that acks `receive_commit`/`receive_reveal` but has no
    `receive_barrier_declaration` tool at all — the barrier-declaration
    call itself must fail against it."""
    mcp = FastMCP("no_barrier_tool_peer")

    @mcp.tool
    def receive_commit(h_commit: str, sent_at: float, deadline_at: float) -> dict:
        return {"acknowledged": True}

    @mcp.tool
    def receive_reveal(move: dict, hint_text: str, sent_at: float, deadline_at: float) -> dict:
        return {"accepted": True, "word_count": len(hint_text.split())}

    port = _free_port()
    threading.Thread(
        target=mcp.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": port, "show_banner": False},
        daemon=True,
    ).start()
    time.sleep(0.5)
    return port


def test_a_failed_barrier_declaration_reaches_technical_loss(config, tmp_path):
    port = _start_commit_and_reveal_only_server()
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    orchestrator.state_machine.transition("COMPUTING_MOVE")

    from cop.domain.board import Position

    with pytest.raises(Exception):  # noqa: B017 - any tool-call failure counts
        asyncio.run(
            orchestrator.commit_and_reveal_to_peer(
                f"http://127.0.0.1:{port}/mcp",
                PlaceBarrier(target=Position(1, 1)),
                False,
                "a test hint",
            )
        )

    assert orchestrator.state_machine.state == "TECHNICAL_LOSS"


def test_a_verify_failure_after_reveal_raises_instead_of_silently_continuing(
    config, tmp_path, monkeypatch
):
    """Sabotage-proof for the defensive local self-check: if `verify()`
    somehow returned `False` after a successful reveal (a genuine local bug,
    not opponent dishonesty), this must raise loudly, not silently proceed
    to WAITING_FOR_OPPONENT as if the turn were clean."""
    port = _free_port()
    server = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "server_trace.jsonl"))
    threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    import cop.orchestrator_commit_reveal as commit_reveal_module

    monkeypatch.setattr(commit_reveal_module, "verify", lambda envelope, h_commit: False)

    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.state_machine.transition("COMPUTING_MOVE")

    with pytest.raises(RuntimeError, match="does not match this side's own earlier commit"):
        asyncio.run(
            client.commit_and_reveal_to_peer(
                f"http://127.0.0.1:{port}/mcp", Move(direction="NORTH"), False, "a test hint"
            )
        )


def test_a_real_round_trip_carries_the_senders_declared_timing_to_the_receiver(config, tmp_path):
    # PRD 15 (ch. 8.4): the wire-level sent_at/deadline_at pair, logged by
    # the receiver's own trace — never used to affect the receiver's own
    # await_with_deadline bound (rule 9), only observed.
    port = _free_port()
    server = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "server_trace.jsonl"))
    threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    before = time.time()
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.state_machine.transition("COMPUTING_MOVE")
    asyncio.run(
        client.commit_and_reveal_to_peer(
            f"http://127.0.0.1:{port}/mcp", Move(direction="NORTH"), False, "a test hint"
        )
    )
    after = time.time()

    server_events = [
        json.loads(line)
        for line in (tmp_path / "server_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    commit_event = next(e for e in server_events if e["event"] == "peer_commit_received")
    reveal_event = next(e for e in server_events if e["event"] == "hint_received")

    assert before <= commit_event["peer_sent_at"] <= after
    assert commit_event["peer_deadline_at"] == pytest.approx(
        commit_event["peer_sent_at"] + config.response_timeout_seconds
    )
    assert before <= reveal_event["peer_sent_at"] <= after
    assert reveal_event["peer_deadline_at"] == pytest.approx(
        reveal_event["peer_sent_at"] + config.response_timeout_seconds
    )


def test_a_deadline_already_expired_on_receipt_logs_an_informational_event_only(config, tmp_path):
    # Untrusted (rule 9): a peer declaring an already-expired deadline is
    # logged for observability, never allowed to change this side's own
    # behavior — the callback itself must not raise or alter state.
    server = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "server_trace.jsonl"))
    already_expired = time.time() - 5.0

    server._on_commit_received("a" * 64, time.time() - 35.0, already_expired)

    events = [
        json.loads(line)
        for line in (tmp_path / "server_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(e["event"] == "peer_declared_deadline_already_expired" for e in events)


def test_a_deadline_still_in_the_future_on_receipt_logs_nothing_extra(config, tmp_path):
    server = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "server_trace.jsonl"))

    server._on_commit_received("a" * 64, time.time(), time.time() + 30.0)

    events = [
        json.loads(line)
        for line in (tmp_path / "server_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert not any(e["event"] == "peer_declared_deadline_already_expired" for e in events)
