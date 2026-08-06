"""Orchestrator (rule 3): wires config, MCP, state machine, deadline tracker, watchdog, log manager.

Real HTTP round-trips (via background threads on free ports), not mocks —
same style as test_mcp_client.py. tmp_path keeps every test's trace log out
of the real repo's logs/ directory.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

import pytest
from fastmcp import Client, FastMCP

from cop import orchestrator as orchestrator_module
from cop.orchestrator import Orchestrator
from cop.planner.deadline import DeadlineExceededError


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_constructing_wires_all_four_subsystems(config, tmp_path):
    orchestrator = Orchestrator(config, log_path=str(tmp_path / "trace.jsonl"))
    assert orchestrator.state_machine.state == "WAITING_FOR_OPPONENT"
    assert orchestrator.server is not None
    assert orchestrator.watchdog is not None
    assert orchestrator.trace is not None


def test_send_to_peer_round_trips_and_resolves_the_turn(config, tmp_path):
    port = _free_port()
    server = Orchestrator(config, log_path=str(tmp_path / "server_trace.jsonl"))
    thread = threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    )
    thread.start()
    time.sleep(0.5)

    client = Orchestrator(config, log_path=str(tmp_path / "client_trace.jsonl"))
    result = asyncio.run(client.send_to_peer(f"http://127.0.0.1:{port}/mcp", col=2, row=3))

    assert result == {"accepted": True, "col": 2, "row": 3}
    assert client.state_machine.state == "WAITING_FOR_OPPONENT"


def test_send_to_peer_deadline_exceeded_transitions_to_technical_loss_and_logs(config, tmp_path):
    # A standalone slow server (not build_server) — deliberately responds
    # slower than the client's timeout, to prove expiry, not connection
    # failure. A refused connection isn't a useful test here: it fails fast
    # with a different exception, never reaching DeadlineExceededError.
    slow = FastMCP("slow_peer")

    @slow.tool
    def receive_position(col: int, row: int) -> dict:
        time.sleep(0.3)
        return {"accepted": True, "col": col, "row": row}

    port = _free_port()
    thread = threading.Thread(
        target=slow.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": port, "show_banner": False},
        daemon=True,
    )
    thread.start()
    time.sleep(0.5)

    fast_config = config.__class__(**{**config.__dict__, "response_timeout_seconds": 0.05})
    orchestrator = Orchestrator(fast_config, log_path=str(tmp_path / "trace.jsonl"))

    with pytest.raises(DeadlineExceededError):
        asyncio.run(orchestrator.send_to_peer(f"http://127.0.0.1:{port}/mcp", col=1, row=1))

    assert orchestrator.state_machine.state == "TECHNICAL_LOSS"

    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "technical_loss" in events


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


def test_watchdog_persist_and_shutdown_write_to_the_orchestrator_trace_log(config, tmp_path):
    orchestrator = Orchestrator(config, log_path=str(tmp_path / "trace.jsonl"))
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


def test_receiving_a_position_feeds_the_orchestrators_watchdog_heartbeat(config, tmp_path):
    # Proves the on_receive wiring, not just that build_server accepts the
    # kwarg: a real call through orchestrator.server must move the
    # orchestrator's own watchdog off a forced-stale timestamp.
    orchestrator = Orchestrator(config, log_path=str(tmp_path / "trace.jsonl"))
    orchestrator.watchdog._last_heartbeat = -10_000.0

    async def _call():
        async with Client(orchestrator.server) as client:
            await client.call_tool("receive_position", {"col": 1, "row": 1})

    asyncio.run(_call())

    assert orchestrator.watchdog._last_heartbeat > -10_000.0
    assert orchestrator.watchdog.check() == "ALIVE"


def test_run_as_server_starts_a_watchdog_monitor_that_shuts_down_on_staleness(
    config, tmp_path, monkeypatch
):
    # rule 7 says "run" a watchdog, not merely construct one: this proves the
    # background poll loop actually calls watchdog.check() while the server
    # runs, and reacts to staleness — without letting a real os._exit(1) end
    # the test process.
    exited = threading.Event()
    monkeypatch.setattr(orchestrator_module.os, "_exit", lambda code: exited.set())

    orchestrator = Orchestrator(config, log_path=str(tmp_path / "trace.jsonl"))
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
    monkeypatch.setattr(orchestrator_module.os, "_exit", lambda code: exited.set())

    orchestrator = Orchestrator(config, log_path=str(tmp_path / "trace.jsonl"))
    orchestrator._start_watchdog_monitor(poll_interval_seconds=0.05)

    for _ in range(5):
        time.sleep(0.05)
        orchestrator.watchdog.heartbeat()

    assert not exited.is_set(), "a live, heartbeating process must not be shut down"
