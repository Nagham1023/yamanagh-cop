"""Rule 36's genuinely bilateral half (ch. 5.4, PRD 7's own Design Question
11): each side verifies the *peer's* own committed-and-revealed data, not a
self-check. The adversarial test below tampers a field the *peer* revealed
(not one this side committed) — proving `run_peer_audit` isn't secretly
just `run_mutual_audit` under a new name, the single most important test in
this file.

Both fixture `Orchestrator`s are cop instances (rule 1/2: this repo can't
run a thief brain) — so every test here passes `role="cop"` explicitly to
`run_peer_audit` rather than relying on its real-deployment default
(`"thief"`), same "this repo's own client talking to its own server, be
honest about it" discipline PRD 6's own tests already established.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

import pytest

from cop.domain.board import Board, Position
from cop.integrity.peer_trace import PeerTrace, run_peer_audit
from cop.orchestrator import Orchestrator
from cop.reasoning.brain_base import Move
from cop.reasoning.cop_brain import CopBrain


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_one_real_exchange_with_final_reveal(config, tmp_path) -> tuple[Orchestrator, Orchestrator]:
    """`client` commits, reveals, and finally sends its own nonces/intents
    to `server` — `server.peer_trace` ends up holding a full, real record
    of what `client` (the "peer," from `server`'s point of view) did.

    `client` is a cop instance too (rule 1/2: this repo can't run a thief
    brain) — so it starts at `config.cop_start`, not `thief_start`; callers
    auditing it must reconstruct from `cop_start` to match. `take_turn()`
    always applies the move to `game_state` *before* committing (so the
    committed `state` reflects the post-move position) — this bypasses
    `take_turn()` to commit a specific, known move directly, so it applies
    the move itself first, matching that same real ordering.
    """
    port = _free_port()
    server = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "server_trace.jsonl"))
    threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    move = Move(direction="E")
    client.game_state.apply(move, client.board)
    client.state_machine.transition("COMPUTING_MOVE")
    url = f"http://127.0.0.1:{port}/mcp"
    asyncio.run(client.commit_and_reveal_to_peer(url, move, False, "quiet by the river"))
    asyncio.run(client.send_final_reveal_to_peer(url))
    return client, server


def test_peer_trace_assembles_a_full_entry_from_three_separate_callbacks():
    # Starts at step 1, not 0 — matching GameState.apply()'s own
    # increment-before-commit ordering (see peer_trace.py's own docstring).
    trace = PeerTrace()
    commit_step = trace.record_commit("a" * 64)
    reveal_step = trace.record_reveal({"type": "move", "direction": "E"}, "quiet by the river")
    assert commit_step == reveal_step == 1

    trace.record_final_reveal({"1": "b" * 32}, {"1": False})

    entry = trace.entries[1]
    assert entry.h_commit == "a" * 64
    assert entry.move == {"type": "move", "direction": "E"}
    assert entry.hint_text == "quiet by the river"
    assert entry.nonce == "b" * 32
    assert entry.intent is False


def test_honest_peer_exchange_passes_the_bilateral_audit(config, tmp_path):
    client, server = _run_one_real_exchange_with_final_reveal(config, tmp_path)

    result = run_peer_audit(
        server.peer_trace, Position(*config.cop_start), server.board, config.barrier_quota, role="cop"
    )

    assert result.passed is True
    assert result.mismatches == []


def test_a_tampered_peer_move_fails_the_bilateral_audit(config, tmp_path):
    """The adversarial milestone: tamper a field the *peer* revealed, then
    confirm the audit — run on the *other* side — catches it. Tampering
    this side's own committed data instead (what `test_audit.py` already
    covers) would prove nothing new about bilaterality."""
    client, server = _run_one_real_exchange_with_final_reveal(config, tmp_path)

    genuine = server.peer_trace.entries[1]
    tampered = PeerTrace()
    tampered.record_commit(genuine.h_commit)
    tampered.record_reveal({"type": "move", "direction": "S"}, genuine.hint_text)  # tampered
    tampered.record_final_reveal({"1": genuine.nonce}, {"1": genuine.intent})

    result = run_peer_audit(
        tampered, Position(*config.cop_start), server.board, config.barrier_quota, role="cop"
    )

    assert result.passed is False
    assert result.mismatches[0]["reason"] == "Hcommit mismatch"


def test_a_missing_final_reveal_fails_the_audit_not_silently_skips(config, tmp_path):
    client, server = _run_one_real_exchange_with_final_reveal(config, tmp_path)

    incomplete = PeerTrace()
    genuine = server.peer_trace.entries[1]
    incomplete.record_commit(genuine.h_commit)
    incomplete.record_reveal(genuine.move, genuine.hint_text)
    # No record_final_reveal call at all — nonce/intent never arrive.

    result = run_peer_audit(
        incomplete, Position(*config.cop_start), server.board, config.barrier_quota, role="cop"
    )

    assert result.passed is False
    assert "missing" in result.mismatches[0]["reason"]


def test_a_malformed_peer_move_fails_the_audit_instead_of_crashing(config):
    trace = PeerTrace()
    trace.record_commit("a" * 64)
    trace.record_reveal({"type": "levitate"}, "quiet by the river")  # not a real move
    trace.record_final_reveal({"1": "b" * 32}, {"1": False})

    result = run_peer_audit(trace, Position(3, 3), Board(size=7), 14, role="cop")

    assert result.passed is False
    assert "malformed or illegal move" in result.mismatches[0]["reason"]


def test_send_final_reveal_to_peer_against_an_unreachable_url_logs_and_reraises(config, tmp_path):
    """No state-machine transition covers Final Reveal (it sits outside the
    per-turn cycle) — a failure here has nowhere legal to land except a
    logged, re-raised exception (`orchestrator_peer_audit.py`'s own
    docstring), never a silently-swallowed `None`."""
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    dead_url = f"http://127.0.0.1:{_free_port()}/mcp"  # nothing listens here

    with pytest.raises(Exception):  # noqa: B017 - deliberately broad: any connection failure counts
        asyncio.run(client.send_final_reveal_to_peer(dead_url))

    events = [json.loads(line)["event"] for line in (tmp_path / "client_trace.jsonl").read_text().splitlines()]
    assert "final_reveal_failed" in events
    assert "final_reveal_sent" not in events


def test_orchestrator_audit_peer_delegates_to_run_peer_audit(config, tmp_path):
    client, server = _run_one_real_exchange_with_final_reveal(config, tmp_path)

    result = server.audit_peer()

    # audit_peer()'s own real-deployment default is role="thief" — the
    # fixture peer is actually a cop (rule 1/2: no thief brain in this
    # repo), so a role mismatch is *expected* here, not a bug: this test
    # only proves the wiring (an AuditResult comes back, referencing the
    # entry this exchange produced), not full pass/fail correctness —
    # that's what the role="cop" tests above already establish.
    assert result.mismatches
    assert result.mismatches[0]["step"] == 1
