"""`report_game()` (PRD 8, rules 32/36): the automatic end-of-game
sequence — final reveal, both audits, league bookkeeping, then the report
send through `ApiGatekeeper`. This repo can never run a thief brain (rule
1/2), so `client` (the one calling `report_game()`) talks to a second real
`Orchestrator` standing in for the peer, matching every other bilateral
test in this repo.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

import pytest

from cop.domain.scoring import Outcome
from cop.orchestrator import Orchestrator
from cop.reasoning.cop_brain import CopBrain


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_peer(config, tmp_path) -> str:
    port = _free_port()
    peer = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "peer_trace.jsonl"))
    threading.Thread(
        target=peer.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)
    return f"http://127.0.0.1:{port}/mcp"


def _report_game(client, peer_url, *, is_counted: bool):
    return asyncio.run(
        client.report_game(
            peer_url,
            Outcome.SURVIVAL,
            is_counted,
            opponent_id=peer_url,
            opponent_cop_repo_url="https://github.com/team-b/cop",
            opponent_thief_repo_url="https://github.com/team-b/thief",
            sub_game_scores={"g01": 5},
            cumulative_score=5,
        )
    )


def test_report_game_returns_cleanly_under_draft_mode(config, tmp_path):
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    # Isolated from Orchestrator.__init__'s own default logs/league_ledger.json
    # — every test in this repo isolates its own file I/O to tmp_path.
    client.league_ledger = client.league_ledger.__class__(path=str(tmp_path / "ledger.json"))
    peer_url = _start_peer(config, tmp_path)

    result = _report_game(client, peer_url, is_counted=True)

    assert result is None  # config/game.toml's own email_mode is "draft"


def test_report_game_records_a_counted_game_when_is_counted_true(config, tmp_path):
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.league_ledger = client.league_ledger.__class__(path=str(tmp_path / "ledger.json"))
    peer_url = _start_peer(config, tmp_path)

    _report_game(client, peer_url, is_counted=True)

    assert client.league_ledger.counted_game_count() == 1
    assert client.league_ledger.is_already_counted(peer_url)


def test_report_game_does_not_record_a_warm_up_game(config, tmp_path):
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.league_ledger = client.league_ledger.__class__(path=str(tmp_path / "ledger.json"))
    peer_url = _start_peer(config, tmp_path)

    _report_game(client, peer_url, is_counted=False)

    assert client.league_ledger.counted_game_count() == 0


def test_report_game_calls_each_step_in_the_documented_order(config, tmp_path):
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.league_ledger = client.league_ledger.__class__(path=str(tmp_path / "ledger.json"))
    peer_url = _start_peer(config, tmp_path)

    call_order = []
    original_final_reveal = client.send_final_reveal_to_peer
    original_audit_peer = client.audit_peer
    original_record = client.league_ledger.record_counted_game
    original_execute = client.gatekeeper.execute

    async def _spy_final_reveal(url):
        call_order.append("final_reveal")
        return await original_final_reveal(url)

    def _spy_audit_peer():
        call_order.append("peer_audit")
        return original_audit_peer()

    def _spy_record(opponent_id):
        call_order.append("league_record")
        return original_record(opponent_id)

    def _spy_execute(api_call, *args, **kwargs):
        call_order.append("gatekeeper_execute")
        return original_execute(api_call, *args, **kwargs)

    client.send_final_reveal_to_peer = _spy_final_reveal
    client.audit_peer = _spy_audit_peer
    client.league_ledger.record_counted_game = _spy_record
    client.gatekeeper.execute = _spy_execute

    _report_game(client, peer_url, is_counted=True)

    assert call_order == ["final_reveal", "peer_audit", "league_record", "gatekeeper_execute"]


def test_report_game_sources_opponent_repo_urls_from_a_completed_negotiation(config, tmp_path, monkeypatch):
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.league_ledger = client.league_ledger.__class__(path=str(tmp_path / "ledger.json"))
    peer_url = _start_peer(config, tmp_path)
    client._opponent_repos = {
        "cop": "https://github.com/team-b/cop", "thief": "https://github.com/team-b/thief",
    }

    captured_bundles = []
    import cop.orchestrator_end_of_game as end_of_game_module

    original_build_result = end_of_game_module.build_result

    def _spy_build_result(bundle):
        captured_bundles.append(bundle)
        return original_build_result(bundle)

    monkeypatch.setattr(end_of_game_module, "build_result", _spy_build_result)

    asyncio.run(
        client.report_game(
            peer_url,
            Outcome.SURVIVAL,
            is_counted=True,
            opponent_id=peer_url,
            sub_game_scores={"g01": 5},
            cumulative_score=5,
        )
    )

    assert len(captured_bundles) == 1
    assert captured_bundles[0].opponent_cop_repo_url == "https://github.com/team-b/cop"
    assert captured_bundles[0].opponent_thief_repo_url == "https://github.com/team-b/thief"


def test_report_game_explicit_override_wins_over_a_completed_negotiation(config, tmp_path, monkeypatch):
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.league_ledger = client.league_ledger.__class__(path=str(tmp_path / "ledger.json"))
    peer_url = _start_peer(config, tmp_path)
    client._opponent_repos = {
        "cop": "https://github.com/from-negotiation/cop", "thief": "https://github.com/from-negotiation/thief",
    }

    captured_bundles = []
    import cop.orchestrator_end_of_game as end_of_game_module

    original_build_result = end_of_game_module.build_result

    def _spy_build_result(bundle):
        captured_bundles.append(bundle)
        return original_build_result(bundle)

    monkeypatch.setattr(end_of_game_module, "build_result", _spy_build_result)

    asyncio.run(
        client.report_game(
            peer_url,
            Outcome.SURVIVAL,
            is_counted=True,
            opponent_id=peer_url,
            sub_game_scores={"g01": 5},
            cumulative_score=5,
            opponent_cop_repo_url="https://github.com/explicit/cop",
            opponent_thief_repo_url="https://github.com/explicit/thief",
        )
    )

    assert captured_bundles[0].opponent_cop_repo_url == "https://github.com/explicit/cop"
    assert captured_bundles[0].opponent_thief_repo_url == "https://github.com/explicit/thief"


def test_report_game_attaches_all_four_table_20_files(config, tmp_path, monkeypatch):
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.league_ledger = client.league_ledger.__class__(path=str(tmp_path / "ledger.json"))
    peer_url = _start_peer(config, tmp_path)

    captured = {}
    import cop.orchestrator_end_of_game as end_of_game_module

    def _spy_send_report_bundle(service, to_addr, subject, body, attachments, email_mode="send"):
        captured["attachments"] = attachments
        return None

    monkeypatch.setattr(end_of_game_module, "send_report_bundle", _spy_send_report_bundle)

    _report_game(client, peer_url, is_counted=True)

    # game_id is the bare Table 20 token (PARAMETERS.md) — declaration_/
    # result_ take only game_id; config_/log_ take game_id *and*
    # sub_game_number separately, appending their own "_g{NN}".
    game_id = client.private_config.group_id
    sub_game_number = client.private_config.sub_game_number
    attachments = captured["attachments"]
    assert set(attachments) == {
        f"declaration_{game_id}.json",
        f"result_{game_id}.json",
        f"config_{game_id}_g{sub_game_number:02d}.json",
        f"log_{game_id}_g{sub_game_number:02d}.json",
    }

    declaration = attachments[f"declaration_{game_id}.json"]
    assert declaration["group_name"] == client.private_config.group_name
    assert declaration["scent_model_sha256"]  # non-empty — a real Step0 declaration, not a stub

    config_payload = attachments[f"config_{game_id}_g{sub_game_number:02d}.json"]
    assert config_payload["schema_version"] == config.schema_version

    log_payload = attachments[f"log_{game_id}_g{sub_game_number:02d}.json"]
    assert isinstance(log_payload, list)
    assert any(entry.get("event") == "nonces_revealed" for entry in log_payload)

    # Every attachment round-trips through JSON cleanly (rule 34: JSON, not free text).
    for payload in attachments.values():
        assert json.loads(json.dumps(payload)) == payload


def test_report_game_raises_when_neither_override_nor_negotiation_is_available(config, tmp_path):
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.league_ledger = client.league_ledger.__class__(path=str(tmp_path / "ledger.json"))
    peer_url = _start_peer(config, tmp_path)
    assert client._opponent_repos is None

    with pytest.raises(ValueError, match="opponent_cop_repo_url"):
        asyncio.run(
            client.report_game(
                peer_url,
                Outcome.SURVIVAL,
                is_counted=True,
                opponent_id=peer_url,
                sub_game_scores={"g01": 5},
                cumulative_score=5,
            )
        )
