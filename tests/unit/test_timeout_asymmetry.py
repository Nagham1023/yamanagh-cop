"""PRD 5's own hardening covered latency tolerance (a response arriving
within the deadline) and drop-after-success (a connection that worked once,
then stopped being reachable) — not this: a peer running a *shorter*
`response_timeout_seconds` than the other side. The exact same real,
genuine response latency produces a technical loss on one side and a
completed, successful exchange on the other — purely a function of each
peer's own configured timeout, never a symptom either side can observe
locally. Rule 35 turns the two contradictory reports into a zero for both,
with no warning before the final audit. This test makes that concrete:
one real slow server, two callers with different timeouts, genuinely
opposite outcomes for the identical event.
"""

from __future__ import annotations

import asyncio
import threading
import time

from fastmcp import FastMCP

from cop.orchestrator import Orchestrator
from cop.planner.deadline import DeadlineExceededError
from cop.reasoning.brain_base import Move
from cop.reasoning.cop_brain import CopBrain


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_slow_peer(delay_seconds: float) -> int:
    slow = FastMCP("genuinely_slow_but_real_peer")

    @slow.tool
    def receive_commit(h_commit: str, sent_at: float, deadline_at: float) -> dict:
        return {"acknowledged": True}

    @slow.tool
    def receive_reveal(move: dict, hint_text: str, sent_at: float, deadline_at: float) -> dict:
        time.sleep(delay_seconds)
        return {"accepted": True, "word_count": len(hint_text.split())}

    port = _free_port()
    threading.Thread(
        target=slow.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": port, "show_banner": False},
        daemon=True,
    ).start()
    time.sleep(0.5)
    return port


def test_the_same_real_response_is_a_technical_loss_for_one_side_and_a_success_for_the_other(config, tmp_path):
    delay_seconds = 1.5
    port = _start_slow_peer(delay_seconds)
    url = f"http://127.0.0.1:{port}/mcp"
    move = Move(direction="NORTH")

    short_config = config.__class__(**{**config.__dict__, "response_timeout_seconds": 0.5})
    short_peer = Orchestrator(short_config, CopBrain(), log_path=str(tmp_path / "short_trace.jsonl"))
    short_peer.state_machine.transition("COMPUTING_MOVE")

    long_config = config.__class__(**{**config.__dict__, "response_timeout_seconds": 5.0})
    long_peer = Orchestrator(long_config, CopBrain(), log_path=str(tmp_path / "long_trace.jsonl"))
    long_peer.state_machine.transition("COMPUTING_MOVE")

    # The short-timeout peer genuinely times out on this real, live server.
    try:
        asyncio.run(short_peer.commit_and_reveal_to_peer(url, move, False, "a test hint"))
        short_raised = False
    except DeadlineExceededError:
        short_raised = True
    assert short_raised, "the short-timeout peer must time out on a genuinely slower-than-its-deadline response"
    assert short_peer.state_machine.state == "TECHNICAL_LOSS"

    # The exact same server, the exact same real 1.5s delay — the
    # long-timeout peer sees a completely normal, successful exchange.
    long_result = asyncio.run(long_peer.commit_and_reveal_to_peer(url, move, False, "a test hint"))
    assert long_result["accepted"] is True
    assert long_peer.state_machine.state == "WAITING_FOR_OPPONENT"

    # The contradiction rule 35 has to reconcile: one peer's own log
    # honestly records a technical loss for an event the other peer's own
    # log honestly records as a routine success. Neither log is lying —
    # each is a true account of what that peer actually observed.
    import json

    short_events = [
        json.loads(line)["event"]
        for line in (tmp_path / "short_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    long_events = [
        json.loads(line)["event"]
        for line in (tmp_path / "long_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "technical_loss" in short_events
    assert "technical_loss" not in long_events
    assert "revealed" in long_events
