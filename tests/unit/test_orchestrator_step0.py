"""The live Step-0 negotiation ceremony (`orchestrator_step0.py`, rules 11,
23, 24, 49) — two real `Orchestrator`s over real HTTP, same bilateral
pattern `test_orchestrator_end_of_game.py` already uses. House rule: at
least one test per layer that proves rejection, not just acceptance — one
per thing `_verify_peer_step0` actually checks.
"""

from __future__ import annotations

import asyncio
import dataclasses
import socket
import threading
import time
from pathlib import Path

import pytest

from cop.integrity.step0 import sign_step0
from cop.integrity.step0_wire import declaration_to_wire
from cop.orchestrator import Orchestrator
from cop.orchestrator_step0 import Step0MismatchError
from cop.reasoning.cop_brain import CopBrain
from cop.tools.mcp_server import build_server

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_SHARED_CONFIG = REPO_ROOT / "config" / "shared" / "config_dev_g01.json"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_peer(config, tmp_path, *, shared_config_path=REAL_SHARED_CONFIG) -> tuple[Orchestrator, str]:
    port = _free_port()
    peer = Orchestrator(
        config,
        CopBrain(),
        log_path=str(tmp_path / "peer_trace.jsonl"),
        shared_config_path=str(shared_config_path),
    )
    threading.Thread(
        target=peer.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)
    return peer, f"http://127.0.0.1:{port}/mcp"


def test_negotiate_step0_succeeds_when_both_sides_genuinely_match(config, tmp_path):
    peer, peer_url = _start_peer(config, tmp_path)
    client = Orchestrator(
        config,
        CopBrain(),
        log_path=str(tmp_path / "client_trace.jsonl"),
        shared_config_path=str(REAL_SHARED_CONFIG),
    )

    asyncio.run(client.negotiate_step0(peer_url))

    assert client.state_machine.state == "WAITING_FOR_OPPONENT"
    assert peer.state_machine.state == "WAITING_FOR_OPPONENT"
    assert client._opponent_repos == dict(peer.private_config.repos)
    assert peer._opponent_repos == dict(client.private_config.repos)


def test_negotiate_step0_rejects_a_config_sha256_mismatch(config, tmp_path):
    # Same logical config, different bytes on disk — proves rule 11's
    # actual enforcement point is the file's bytes, not the parsed object.
    tampered = tmp_path / "tampered_config.json"
    tampered.write_bytes(REAL_SHARED_CONFIG.read_bytes() + b" ")

    peer, peer_url = _start_peer(config, tmp_path, shared_config_path=tampered)
    client = Orchestrator(
        config,
        CopBrain(),
        log_path=str(tmp_path / "client_trace.jsonl"),
        shared_config_path=str(REAL_SHARED_CONFIG),
    )

    with pytest.raises(Step0MismatchError):
        asyncio.run(client.negotiate_step0(peer_url))

    assert client.state_machine.state == "TECHNICAL_LOSS"
    assert peer.state_machine.state == "TECHNICAL_LOSS"


def test_negotiate_step0_rejects_a_scent_model_mismatch(config, tmp_path):
    # Identical config file bytes, a genuinely different decay_rate in the
    # object actually driving this side's own ScentField — proves the
    # scent-model lock is a real, independent check, not just a restatement
    # of config_sha256.
    mismatched_scent_config = dataclasses.replace(config, scent_decay_rate=0.25)

    peer, peer_url = _start_peer(config, tmp_path)
    client = Orchestrator(
        mismatched_scent_config,
        CopBrain(),
        log_path=str(tmp_path / "client_trace.jsonl"),
        shared_config_path=str(REAL_SHARED_CONFIG),
    )

    with pytest.raises(Step0MismatchError):
        asyncio.run(client.negotiate_step0(peer_url))

    assert client.state_machine.state == "TECHNICAL_LOSS"
    assert peer.state_machine.state == "TECHNICAL_LOSS"


def test_negotiate_step0_rejects_a_response_missing_a_required_key(config, tmp_path):
    # A raw KeyError from a malformed *response* dict (distinct from a
    # malformed *declaration*/*repos* shape inside an otherwise well-formed
    # response) — negotiate_step0's own "response['repos']" lookup, not
    # _verify_peer_step0's.
    port = _free_port()
    mcp = build_server(config, on_step0=lambda declaration, signature, repos: {"declaration": declaration})
    threading.Thread(
        target=mcp.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": port, "show_banner": False},
        daemon=True,
    ).start()
    time.sleep(0.5)
    peer_url = f"http://127.0.0.1:{port}/mcp"

    client = Orchestrator(
        config,
        CopBrain(),
        log_path=str(tmp_path / "client_trace.jsonl"),
        shared_config_path=str(REAL_SHARED_CONFIG),
    )

    with pytest.raises(Step0MismatchError, match="malformed step0 response"):
        asyncio.run(client.negotiate_step0(peer_url))

    assert client.state_machine.state == "TECHNICAL_LOSS"


def test_verify_peer_step0_rejects_a_forged_signature(config, tmp_path):
    # Direct, single-instance check — a tampered/forged signature must be
    # caught without needing two live servers to prove it.
    client = Orchestrator(
        config,
        CopBrain(),
        log_path=str(tmp_path / "client_trace.jsonl"),
        shared_config_path=str(REAL_SHARED_CONFIG),
    )
    own_declaration = client._build_own_step0()
    own_repos = {"cop": "https://example.com/cop", "thief": "https://example.com/thief"}

    with pytest.raises(Step0MismatchError, match="signature"):
        client._verify_peer_step0(
            declaration_to_wire(own_declaration), "not-the-real-signature", own_repos
        )


def test_verify_peer_step0_rejects_a_repos_payload_missing_a_required_key(config, tmp_path):
    # The rule-auditor's own finding (PRD 9 review): a malformed `repos`
    # shape must not reach `self._opponent_repos` unvalidated — it would
    # otherwise surface as an uncaught KeyError inside report_game() at
    # the end of a real match instead of a clean, logged rejection.
    client = Orchestrator(
        config,
        CopBrain(),
        log_path=str(tmp_path / "client_trace.jsonl"),
        shared_config_path=str(REAL_SHARED_CONFIG),
    )
    own_declaration = client._build_own_step0()
    signature = sign_step0(own_declaration)

    with pytest.raises(Step0MismatchError, match="repos"):
        client._verify_peer_step0(
            declaration_to_wire(own_declaration), signature, {"cop": "https://example.com/cop"}
        )


def test_verify_peer_step0_rejects_a_non_string_repos_value(config, tmp_path):
    client = Orchestrator(
        config,
        CopBrain(),
        log_path=str(tmp_path / "client_trace.jsonl"),
        shared_config_path=str(REAL_SHARED_CONFIG),
    )
    own_declaration = client._build_own_step0()
    signature = sign_step0(own_declaration)

    with pytest.raises(Step0MismatchError, match="repos"):
        client._verify_peer_step0(
            declaration_to_wire(own_declaration), signature, {"cop": 123, "thief": "https://example.com/thief"}
        )
