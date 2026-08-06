"""PRD 2's actual milestone, automated: two real OS processes (rule 1),
proven not to share state (rule 2), round-tripping a message over
localhost. `_server_process.py` is the helper each spawned process runs.
"""

from __future__ import annotations

import asyncio
import json
import time

from _helpers import REPO_CONFIG
from _helpers import free_port as _free_port
from _helpers import spawn_server as _spawn_server
from _helpers import wait_for_port as _wait_for_port

from cop.orchestrator import Orchestrator
from cop.planner.state_machine import PeerStateMachine
from cop.reasoning.cop_brain import CopBrain
from cop.shared.config import GameConfig
from cop.tools.mcp_client import send_position


def test_message_from_process_a_is_received_and_decoded_by_process_b(tmp_path):
    """The milestone: an agent-A-initiated message, received and decoded by agent B."""
    port_b = _free_port()
    log_b = tmp_path / "b_trace.jsonl"
    proc_b = _spawn_server(port_b, log_b)
    try:
        _wait_for_port(port_b)
        data = asyncio.run(send_position(f"http://127.0.0.1:{port_b}/mcp", col=4, row=5))
        assert data == {"accepted": True, "col": 4, "row": 5}
    finally:
        proc_b.terminate()
        proc_b.wait(timeout=5)


def test_the_two_processes_are_genuinely_separate_not_shared_state(tmp_path):
    """Rule 2: proven, not assumed — two distinct PIDs, two independent logs."""
    port_a, port_b = _free_port(), _free_port()
    log_a, log_b = tmp_path / "a_trace.jsonl", tmp_path / "b_trace.jsonl"
    proc_a, proc_b = _spawn_server(port_a, log_a), _spawn_server(port_b, log_b)
    try:
        _wait_for_port(port_a)
        _wait_for_port(port_b)
        assert proc_a.pid != proc_b.pid

        a_first = json.loads(log_a.read_text(encoding="utf-8").splitlines()[0])
        b_first = json.loads(log_b.read_text(encoding="utf-8").splitlines()[0])
        assert a_first["pid"] == proc_a.pid
        assert b_first["pid"] == proc_b.pid
        assert a_first["pid"] != b_first["pid"]
    finally:
        proc_a.terminate()
        proc_a.wait(timeout=5)
        proc_b.terminate()
        proc_b.wait(timeout=5)


def test_killing_the_peer_produces_a_clean_technical_loss_not_a_hang(tmp_path):
    """Kill process B mid-flight; process A's own Orchestrator must not hang,
    must land in TECHNICAL_LOSS, and must have an intact log to show for it —
    the actual PRD 2 acceptance criterion, not just the deadline unit test."""
    port_b = _free_port()
    log_b = tmp_path / "b_trace.jsonl"
    proc_b = _spawn_server(port_b, log_b)
    _wait_for_port(port_b)
    proc_b.kill()
    proc_b.wait(timeout=5)

    config = GameConfig.from_file(REPO_CONFIG)
    fast_config = config.__class__(**{**config.__dict__, "response_timeout_seconds": 1.0})
    orchestrator = Orchestrator(fast_config, CopBrain(), log_path=str(tmp_path / "a_trace.jsonl"))
    orchestrator.state_machine.transition("COMPUTING_MOVE")  # send_to_peer only owns SENDING onward

    start = time.monotonic()
    try:
        asyncio.run(orchestrator.send_to_peer(f"http://127.0.0.1:{port_b}/mcp", col=1, row=1))
        raised = False
    except Exception:
        raised = True
    elapsed = time.monotonic() - start

    assert raised, "a killed peer must not be silently treated as a success"
    assert elapsed < 5.0, "must not hang toward the full response_timeout_seconds"
    assert orchestrator.state_machine.state == "TECHNICAL_LOSS"

    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "a_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "technical_loss" in events


def test_watchdog_fires_and_extracts_data_on_a_forced_crash(tmp_path):
    """Simulates the watchdog noticing its own process's main loop has
    stalled (rule 7) — a stale heartbeat, not an external kill, since the
    watchdog's job is to detect *this* process freezing, not the peer's."""
    config = GameConfig.from_file(REPO_CONFIG)
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    orchestrator.watchdog._last_heartbeat = -10_000.0  # force staleness deterministically

    status = orchestrator.watchdog.check()

    assert status == "SHUTDOWN"
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "watchdog_persist_state" in events
    assert "watchdog_controlled_shutdown" in events


def test_illegal_state_transition_mid_exchange_is_rejected_not_absorbed():
    """Rule 5, exercised the way a real turn loop would trip it: trying to
    jump straight to TURN_RESOLVED without ever sending anything."""
    machine = PeerStateMachine()
    try:
        machine.transition("TURN_RESOLVED")
        raised = False
    except ValueError:
        raised = True

    assert raised
    assert machine.state == "WAITING_FOR_OPPONENT", "a rejected transition must not partially apply"
