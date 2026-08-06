"""Orchestrator watchdog integration (rule 7): wiring, heartbeats, and the
background poll loop that makes "run a watchdog" true at runtime, not just
on paper. Split out of test_orchestrator.py, which grew past the 150-line
house cap carrying both client-role and watchdog concerns.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time

from fastmcp import Client

from cop import orchestrator_server as orchestrator_server_module
from cop.orchestrator import Orchestrator
from cop.reasoning.cop_brain import CopBrain


def test_watchdog_persist_and_shutdown_write_to_the_orchestrator_trace_log(config, tmp_path):
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    # Force staleness deterministically rather than sleeping past the real
    # threshold — Watchdog doesn't expose a public "force stale" hook, so
    # this reaches into its private state directly (same package, pragmatic).
    orchestrator.watchdog._last_heartbeat = -10_000.0

    assert orchestrator.watchdog.check() == "SHUTDOWN"

    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "watchdog_persist_state" in events
    assert "watchdog_controlled_shutdown" in events


def test_receiving_a_hint_feeds_the_orchestrators_watchdog_heartbeat(config, tmp_path):
    # Proves the on_receive wiring, not just that build_server accepts the
    # kwarg: a real call through orchestrator.server must move the
    # orchestrator's own watchdog off a forced-stale timestamp.
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    orchestrator.watchdog._last_heartbeat = -10_000.0

    async def _call():
        async with Client(orchestrator.server) as client:
            await client.call_tool(
                "receive_hint", {"text": "a test hint", "scent_report": "Scent strongest to the north west."}
            )

    asyncio.run(_call())

    assert orchestrator.watchdog._last_heartbeat > -10_000.0
    assert orchestrator.watchdog.check() == "ALIVE"


def test_on_connection_received_feeds_the_heartbeat_and_logs_the_ip(config, tmp_path):
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    orchestrator.watchdog._last_heartbeat = -10_000.0

    orchestrator._on_connection_received("203.0.113.7")

    assert orchestrator.watchdog._last_heartbeat > -10_000.0
    events = [
        json.loads(line)
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (connection_event,) = [e for e in events if e["event"] == "connection_received"]
    assert connection_event["ip"] == "203.0.113.7"


def test_run_as_server_starts_a_watchdog_monitor_that_shuts_down_on_staleness(
    config, tmp_path, monkeypatch
):
    # rule 7 says "run" a watchdog, not merely construct one: this proves the
    # background poll loop actually calls watchdog.check() while the server
    # runs, and reacts to staleness — without letting a real os._exit(1) end
    # the test process.
    exited = threading.Event()
    monkeypatch.setattr(orchestrator_server_module.os, "_exit", lambda code: exited.set())

    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    orchestrator._start_watchdog_monitor(poll_interval_seconds=0.05)

    orchestrator.watchdog._last_heartbeat = -10_000.0

    assert exited.wait(timeout=2.0), "watchdog monitor never detected staleness and shut down"

    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "watchdog_controlled_shutdown" in events

    # The monitor thread is a daemon that loops forever by design (it's meant
    # to outlive `run_as_server` for the whole process lifetime) and outlives
    # this test. Restore its heartbeat before returning so it stops tripping
    # `os._exit` on every future poll — otherwise, once `monkeypatch` reverts
    # `os._exit` to the real one after this test ends, the leaked thread would
    # call the *real* `os._exit(1)` and kill the entire pytest process.
    orchestrator.watchdog.heartbeat()
    time.sleep(0.15)


def test_watchdog_monitor_stays_alive_while_heartbeats_keep_arriving(config, tmp_path, monkeypatch):
    exited = threading.Event()
    monkeypatch.setattr(orchestrator_server_module.os, "_exit", lambda code: exited.set())

    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    orchestrator._start_watchdog_monitor(poll_interval_seconds=0.05)

    for _ in range(5):
        time.sleep(0.05)
        orchestrator.watchdog.heartbeat()

    assert not exited.is_set(), "a live, heartbeating process must not be shut down"
