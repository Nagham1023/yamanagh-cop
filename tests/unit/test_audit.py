"""Rule 19 (**[FATAL]**): the mutual audit must catch any hash mismatch, no
exceptions. The adversarial test below — a log where one turn's committed
`Hcommit` doesn't match what the now-revealed fields recompute to — is the
single most important test in PRD 6, matching this project's own repeated
"a verifier that never rejects anything is worthless" rule.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

from cop.integrity.audit import run_mutual_audit
from cop.orchestrator import Orchestrator
from cop.reasoning.brain_base import Move
from cop.reasoning.cop_brain import CopBrain


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_one_real_committed_turn(config, tmp_path) -> Orchestrator:
    """A genuine two-Orchestrator commit+reveal exchange — the client's own
    trace log and retained nonces are what `run_mutual_audit` replays."""
    port = _free_port()
    server = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "server_trace.jsonl"))
    threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.state_machine.transition("COMPUTING_MOVE")
    asyncio.run(
        client.commit_and_reveal_to_peer(
            f"http://127.0.0.1:{port}/mcp", Move(direction="NORTH"), False, "quiet by the river"
        )
    )
    return client


def test_honest_turn_passes_the_audit(config, tmp_path):
    client = _run_one_real_committed_turn(config, tmp_path)

    result = run_mutual_audit(tmp_path / "client_trace.jsonl", client._pending_nonces)

    assert result.passed is True
    assert result.mismatches == []


def test_honest_turn_passes_the_audit_with_string_keyed_nonces(config, tmp_path):
    """`receive_final_reveal`'s own wire payload is necessarily string-keyed
    (JSON object keys are always strings) — proves `run_mutual_audit`
    normalizes the key type rather than silently missing every lookup, the
    latent bug rule-auditor's own review caught before any caller wired the
    wire-sourced path."""
    client = _run_one_real_committed_turn(config, tmp_path)
    wire_shaped_nonces = {str(step): nonce for step, nonce in client._pending_nonces.items()}

    result = run_mutual_audit(tmp_path / "client_trace.jsonl", wire_shaped_nonces)

    assert result.passed is True
    assert result.mismatches == []


def test_a_tampered_commit_entry_fails_the_audit(config, tmp_path):
    """The adversarial milestone: deliberately tamper one committed field
    after the fact, before the nonce reveal, and confirm the audit rejects
    it — not just that the honest path passes."""
    client = _run_one_real_committed_turn(config, tmp_path)
    trace_path = tmp_path / "client_trace.jsonl"

    lines = trace_path.read_text(encoding="utf-8").splitlines()
    tampered_lines = []
    for line in lines:
        entry = json.loads(line)
        if entry["event"] == "committing":
            entry["move"] = {"type": "move", "direction": "SOUTH"}  # tampered after commit
        tampered_lines.append(json.dumps(entry))
    trace_path.write_text("\n".join(tampered_lines) + "\n", encoding="utf-8")

    result = run_mutual_audit(trace_path, client._pending_nonces)

    assert result.passed is False
    assert result.mismatches[0]["reason"] == "Hcommit mismatch"


def test_a_missing_nonce_fails_the_audit(config, tmp_path):
    _run_one_real_committed_turn(config, tmp_path)

    result = run_mutual_audit(tmp_path / "client_trace.jsonl", nonces={})

    assert result.passed is False
    assert result.mismatches[0]["reason"] == "no nonce revealed for this step"


def test_a_log_with_no_committing_entries_passes_vacuously(tmp_path):
    empty_log = tmp_path / "empty_trace.jsonl"
    empty_log.write_text("", encoding="utf-8")

    result = run_mutual_audit(empty_log, nonces={})

    assert result.passed is True
    assert result.mismatches == []
