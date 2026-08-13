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


def test_watchdog_persist_state_snapshots_real_live_game_state_not_just_the_phase(config, tmp_path):
    # PRD 15 (ch. 8.4): "State Persistence" must mean real state, not just
    # the state-machine's own phase name — set up genuinely non-default
    # own_pos/target_pos/barriers/steps_taken first, so this actually
    # proves the snapshot is live data, not a coincidental match on defaults.
    from cop.domain.board import Position
    from cop.reasoning.brain_base import Move

    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    start = orchestrator.game_state.own_pos
    orchestrator.game_state.apply(Move(direction="E"), orchestrator.board)
    orchestrator.game_state.target_pos = Position(3, 3)
    orchestrator.game_state.barriers.placed.add(Position(2, 2))
    orchestrator.game_state.steps_taken = 4
    orchestrator.watchdog._last_heartbeat = -10_000.0

    assert orchestrator.watchdog.check() == "SHUTDOWN"

    events = [
        json.loads(line)
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (snapshot,) = [e for e in events if e["event"] == "watchdog_persist_state"]
    assert snapshot["own_pos"] == [start.col + 1, start.row]
    assert snapshot["target_pos"] == [3, 3]
    assert snapshot["barriers_placed"] == [[2, 2]]
    assert snapshot["steps_taken"] == 4


def test_receiving_a_reveal_feeds_the_orchestrators_watchdog_heartbeat(config, tmp_path):
    # Proves the on_receive wiring, not just that build_server accepts the
    # kwarg: a real call through orchestrator.server must move the
    # orchestrator's own watchdog off a forced-stale timestamp.
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    orchestrator.watchdog._last_heartbeat = -10_000.0

    async def _call():
        async with Client(orchestrator.server) as client:
            await client.call_tool(
                "receive_reveal",
                {
                    "move": {"type": "move", "direction": "NORTH"},
                    "hint_text": "a test hint",
                    "sent_at": 1.0,
                    "deadline_at": 31.0,
                },
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

    # The monitor thread would otherwise loop forever by design (rule 7:
    # meant to outlive a single match for the whole process lifetime) and
    # outlive this test — `tests/conftest.py`'s own autouse
    # `_stop_watchdog_monitors_after_test` fixture (PRD 15) now calls
    # `stop_watchdog_monitor()` on every orchestrator after each test, so
    # no manual heartbeat-restoration workaround is needed here anymore.


def test_stop_watchdog_monitor_actually_stops_the_background_poll_loop(config, tmp_path, monkeypatch):
    # Proves stop_watchdog_monitor() itself, not just that the conftest
    # fixture calls it: force staleness *after* stopping — if the loop
    # were still polling, os._exit would fire; it must not.
    exited = threading.Event()
    monkeypatch.setattr(orchestrator_server_module.os, "_exit", lambda code: exited.set())

    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    orchestrator._start_watchdog_monitor(poll_interval_seconds=0.02)
    time.sleep(0.05)  # let the loop enter its first real wait

    orchestrator.stop_watchdog_monitor()
    orchestrator.watchdog._last_heartbeat = -10_000.0
    time.sleep(0.2)  # comfortably past several would-be poll intervals

    assert not exited.is_set(), "a stopped monitor must never check again, let alone shut down"


def test_watchdog_monitor_stays_alive_while_heartbeats_keep_arriving(config, tmp_path, monkeypatch):
    exited = threading.Event()
    monkeypatch.setattr(orchestrator_server_module.os, "_exit", lambda code: exited.set())

    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    orchestrator._start_watchdog_monitor(poll_interval_seconds=0.05)

    for _ in range(5):
        time.sleep(0.05)
        orchestrator.watchdog.heartbeat()

    assert not exited.is_set(), "a live, heartbeating process must not be shut down"
