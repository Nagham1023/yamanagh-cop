"""`_await_peer_final_reveal` (orchestrator_peer_audit.py): the fix for a
real race found live — `report_game()` used to call `audit_peer()` the
instant this side's own outcome was known, without checking whether the
peer's independently-timed Final Reveal had actually arrived yet. A clean,
fast match let this side's own survival trigger moments before the peer's
asynchronous Final Reveal landed, so `audit_peer()` ran against a
`peer_trace` still missing every step's nonce — a false "tampered: true"
on data that was genuinely fine once it did arrive (confirmed separately
by replaying a real opponent's own log through `run_peer_audit` directly:
zero mismatches).

`play_game()` captures `self._peer_final_reveal_loop` once, at start —
these tests set it directly instead, mirroring exactly what that capture
achieves without needing a full `play_game()` run.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time

from cop.orchestrator import Orchestrator
from cop.reasoning.cop_brain import CopBrain


def test_await_peer_final_reveal_returns_immediately_when_already_received(config, tmp_path):
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    orchestrator._peer_final_reveal_received = True

    start = time.time()
    asyncio.run(orchestrator._await_peer_final_reveal(timeout_seconds=5.0))
    elapsed = time.time() - start

    assert elapsed < 0.5  # no real wait -- the fast path fired
    trace_path = tmp_path / "trace.jsonl"
    # The fast path logs nothing at all -- an absent file is itself part of
    # proving no wait (and no timeout log) happened.
    if trace_path.exists():
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        assert not any(e["event"] == "peer_final_reveal_wait_timed_out" for e in events)


def test_await_peer_final_reveal_wakes_up_when_the_reveal_arrives_from_another_thread(
    config, tmp_path
):
    # Reproduces the real mechanism: _on_final_reveal_received runs on the
    # MCP server's own OS thread (here, a plain background thread standing
    # in for it) and must wake a waiter parked on a *different* event loop
    # via call_soon_threadsafe -- a bare .set() from the wrong thread would
    # silently do nothing (orchestrator_capture.py's own docstring already
    # documents this exact pitfall for the sibling capture-response event).
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))

    async def wait_then_check() -> bool:
        orchestrator._peer_final_reveal_loop = asyncio.get_running_loop()

        def deliver_late() -> None:
            time.sleep(0.2)
            orchestrator._on_final_reveal_received(nonces={}, intents={})

        threading.Thread(target=deliver_late, daemon=True).start()

        start = time.time()
        await orchestrator._await_peer_final_reveal(timeout_seconds=5.0)
        elapsed = time.time() - start
        return elapsed < 2.0  # woke up promptly on the signal, not the 5s deadline

    woke_up_promptly = asyncio.run(wait_then_check())

    assert woke_up_promptly
    assert orchestrator._peer_final_reveal_received is True
    events = [
        json.loads(line)
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert not any(e["event"] == "peer_final_reveal_wait_timed_out" for e in events)


def test_await_peer_final_reveal_times_out_and_logs_when_the_peer_never_sends_one(
    config, tmp_path
):
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))

    async def wait_with_short_timeout() -> None:
        orchestrator._peer_final_reveal_loop = asyncio.get_running_loop()
        await orchestrator._await_peer_final_reveal(timeout_seconds=0.2)

    asyncio.run(wait_with_short_timeout())  # must not raise -- a timeout here isn't fatal

    assert orchestrator._peer_final_reveal_received is False
    events = [
        json.loads(line)
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (timeout_event,) = [e for e in events if e["event"] == "peer_final_reveal_wait_timed_out"]
    assert timeout_event["timeout_seconds"] == 0.2
