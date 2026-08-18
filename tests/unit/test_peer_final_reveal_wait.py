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


def test_a_reveal_that_arrives_just_after_a_tight_timeout_reproduces_the_false_forfeit(
    config, tmp_path
):
    # Reproduces the real 2026-08-18 live incident on demand, scaled down for
    # a fast unit test: a genuinely in-flight peer reveal that lands a hair
    # after this side's own wait gives up. `config/shared/config_dev_g01.json`'s
    # `response_timeout_sec` was 30 in that incident and the reveal arrived
    # ~0.26s late; here the ratio (timeout, then delivery ~1.5x the timeout
    # later) is what's reproduced, not the literal 30s -- a 30s sleep has no
    # place in this suite. The assertion that matters: at the moment the
    # wait gives up, `_peer_final_reveal_received` is still False, which is
    # exactly the condition that makes `_finish_report_game`'s subsequent
    # `audit_peer()` call see incomplete peer data and record
    # `peer_audit_passed=False` / `tampered=True` on a reveal that was
    # genuinely fine and simply hadn't landed yet.
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))

    async def wait_then_check() -> bool:
        orchestrator._peer_final_reveal_loop = asyncio.get_running_loop()

        def deliver_just_late() -> None:
            time.sleep(0.3)  # later than the 0.2s wait below -- the real incident's own ratio
            orchestrator._on_final_reveal_received(nonces={}, intents={})

        thread = threading.Thread(target=deliver_just_late, daemon=True)
        thread.start()
        await orchestrator._await_peer_final_reveal(timeout_seconds=0.2)
        # Captured right here, at the moment that matters -- the false-forfeit
        # condition is about state at the *end of the wait*, not afterward.
        received_when_wait_gave_up = orchestrator._peer_final_reveal_received
        # Keep this coroutine's loop alive until the stray late delivery has
        # actually landed, rather than let asyncio.run() close it out from
        # under a background thread's call_soon_threadsafe (a real
        # RuntimeError: Event loop is closed, harmless but noisy) -- purely
        # test hygiene, no bearing on the assertion already captured above.
        thread.join()
        return received_when_wait_gave_up

    received_when_wait_gave_up = asyncio.run(wait_then_check())

    # The false-forfeit condition, reproduced: the wait already gave up
    # before the (genuinely fine) reveal arrived.
    assert received_when_wait_gave_up is False
    events = [
        json.loads(line)
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(e["event"] == "peer_final_reveal_wait_timed_out" for e in events)


def test_the_same_late_reveal_is_absorbed_cleanly_once_the_timeout_has_real_margin(
    config, tmp_path
):
    # The fix, proven against the identical delivery timing as the test
    # above -- only the timeout changed, mirroring config_dev_g01.json's
    # real response_timeout_sec move (30 -> 90, a 3x margin increase): a
    # reveal that arrives at the same "just late" moment is now caught by
    # the wait itself, never reaches the false-forfeit condition at all.
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))

    async def wait_then_check() -> None:
        orchestrator._peer_final_reveal_loop = asyncio.get_running_loop()

        def deliver_just_late() -> None:
            time.sleep(0.3)  # identical delivery timing to the reproduction above
            orchestrator._on_final_reveal_received(nonces={}, intents={})

        threading.Thread(target=deliver_just_late, daemon=True).start()
        await orchestrator._await_peer_final_reveal(timeout_seconds=0.6)  # 3x margin, not 0.2s

    asyncio.run(wait_then_check())

    assert orchestrator._peer_final_reveal_received is True
    events = [
        json.loads(line)
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert not any(e["event"] == "peer_final_reveal_wait_timed_out" for e in events)
