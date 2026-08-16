"""The passive half of Step-0 negotiation (`orchestrator_step0_wait.py`,
PRD 10) — `await_passive_step0`, the CLI's non-initiating side. Reuses
PRD 8's cross-thread `asyncio.Event` pattern (`orchestrator_capture.py`);
this file exercises that same shape of bug directly, not just indirectly
through a CLI test, given that pattern's own history of a real,
reproducible hang the first time it was attempted without care.
"""

from __future__ import annotations

import asyncio
import dataclasses
import socket
import threading
import time
from pathlib import Path

import pytest

from cop.orchestrator import Orchestrator
from cop.orchestrator_step0 import Step0MismatchError
from cop.reasoning.cop_brain import CopBrain

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_SHARED_CONFIG = REPO_ROOT / "config" / "shared" / "config_dev_g01.json"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_peer(config, tmp_path) -> tuple[Orchestrator, str]:
    port = _free_port()
    peer = Orchestrator(
        config,
        CopBrain(),
        log_path=str(tmp_path / "peer_trace.jsonl"),
        shared_config_path=str(REAL_SHARED_CONFIG),
    )
    threading.Thread(
        target=peer.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)
    return peer, f"http://127.0.0.1:{port}/mcp"


def test_await_passive_step0_succeeds_when_the_peer_initiates(config, tmp_path):
    peer, peer_url = _start_peer(config, tmp_path)
    client = Orchestrator(
        config,
        CopBrain(),
        log_path=str(tmp_path / "client_trace.jsonl"),
        shared_config_path=str(REAL_SHARED_CONFIG),
    )

    async def _run():
        await asyncio.gather(peer.await_passive_step0(30.0), client.negotiate_step0(peer_url))

    asyncio.run(_run())

    assert peer.state_machine.state == "WAITING_FOR_OPPONENT"
    assert client.state_machine.state == "WAITING_FOR_OPPONENT"
    assert peer._opponent_repos == dict(client.private_config.repos)


def test_await_passive_step0_times_out_cleanly_when_nobody_initiates(config, tmp_path):
    peer, _peer_url = _start_peer(config, tmp_path)

    start = time.monotonic()
    with pytest.raises(Step0MismatchError, match="no peer initiated"):
        asyncio.run(peer.await_passive_step0(0.3))
    elapsed = time.monotonic() - start

    assert elapsed < 5.0  # a clean, bounded timeout — not a hang
    assert peer.state_machine.state == "TECHNICAL_LOSS"


def test_await_passive_step0_relays_a_mismatch_the_callback_detected(config, tmp_path):
    # Identical config file bytes, a genuinely different scent formula on
    # the initiator's side — proves await_passive_step0 learns about a
    # rejected negotiation too, not just a successful one.
    peer, peer_url = _start_peer(config, tmp_path)
    mismatched_config = dataclasses.replace(config, scent_decay_rate=0.25)
    client = Orchestrator(
        mismatched_config,
        CopBrain(),
        log_path=str(tmp_path / "client_trace.jsonl"),
        shared_config_path=str(REAL_SHARED_CONFIG),
    )

    async def _run():
        return await asyncio.gather(
            peer.await_passive_step0(30.0), client.negotiate_step0(peer_url),
            return_exceptions=True,
        )

    passive_result, initiator_result = asyncio.run(_run())

    assert isinstance(passive_result, Step0MismatchError)
    assert isinstance(initiator_result, Step0MismatchError)
    assert peer.state_machine.state == "TECHNICAL_LOSS"
    assert client.state_machine.state == "TECHNICAL_LOSS"


def test_await_passive_step0_does_not_discard_a_negotiation_that_already_completed(config, tmp_path):
    # rule-auditor's own reproduced finding: in a real CLI run, the peer's
    # own negotiate_step0 can complete in full (during run_as_server's own
    # startup grace window) before await_passive_step0 is ever called. The
    # passive side must recognize this and return immediately — not reset
    # an already-correct state and wait out the full timeout for an event
    # nothing will ever set again.
    peer, peer_url = _start_peer(config, tmp_path)
    client = Orchestrator(
        config,
        CopBrain(),
        log_path=str(tmp_path / "client_trace.jsonl"),
        shared_config_path=str(REAL_SHARED_CONFIG),
    )

    asyncio.run(client.negotiate_step0(peer_url))
    assert peer.state_machine.state == "WAITING_FOR_OPPONENT"  # already resolved

    start = time.monotonic()
    asyncio.run(peer.await_passive_step0(30.0))
    elapsed = time.monotonic() - start

    assert elapsed < 1.0  # returned immediately — never actually waited
    assert peer.state_machine.state == "WAITING_FOR_OPPONENT"  # untouched, not reset
    assert peer._opponent_repos == dict(client.private_config.repos)


def test_await_passive_step0_keeps_the_watchdog_alive_through_a_wait_longer_than_its_own_threshold(
    config, tmp_path
):
    # The real bug this closes: found live — a real match's own passive
    # side self-terminated (watchdog_controlled_shutdown) well under a
    # minute into a legitimate, up-to-step0_wait_seconds wait for the
    # opponent to dial in, because nothing about the wait ever heartbeated
    # the watchdog. Same shape as cli_peer_match_body.py's own
    # _sleep_with_heartbeats regression test: a short threshold, a total
    # wait well past it, nobody ever signals the event, and the watchdog
    # must still read ALIVE throughout rather than going stale mid-wait.
    fast_config = dataclasses.replace(config, watchdog_threshold_seconds=0.3)
    peer = Orchestrator(
        fast_config,
        CopBrain(),
        log_path=str(tmp_path / "peer_trace.jsonl"),
        shared_config_path=str(REAL_SHARED_CONFIG),
    )

    with pytest.raises(Step0MismatchError, match="no peer initiated"):
        asyncio.run(peer.await_passive_step0(1.0))

    assert peer.watchdog.check() == "ALIVE"


def test_await_passive_step0_relays_a_failure_that_already_completed(config, tmp_path):
    peer, peer_url = _start_peer(config, tmp_path)
    mismatched_config = dataclasses.replace(config, scent_decay_rate=0.25)
    client = Orchestrator(
        mismatched_config,
        CopBrain(),
        log_path=str(tmp_path / "client_trace.jsonl"),
        shared_config_path=str(REAL_SHARED_CONFIG),
    )

    with pytest.raises(Step0MismatchError):
        asyncio.run(client.negotiate_step0(peer_url))
    assert peer.state_machine.state == "TECHNICAL_LOSS"  # already resolved, as a failure

    start = time.monotonic()
    with pytest.raises(Step0MismatchError):
        asyncio.run(peer.await_passive_step0(30.0))
    elapsed = time.monotonic() - start

    assert elapsed < 1.0
    assert peer.state_machine.state == "TECHNICAL_LOSS"  # untouched
