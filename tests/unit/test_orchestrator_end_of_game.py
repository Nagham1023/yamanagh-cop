"""`report_game()` (PRD 8, rules 32/36): the automatic end-of-game
sequence — final reveal, both audits, league bookkeeping, then the report
send through `ApiGatekeeper`. This repo can never run a thief brain (rule
1/2), so `client` (the one calling `report_game()`) talks to a second real
`Orchestrator` standing in for the peer, matching every other bilateral
test in this repo.

PRD 16: `client._opponent_declaration` is set directly rather than run
through a real Step-0 negotiation — `_start_peer` doesn't run one — the
same "bypass negotiation for this one piece" shortcut
`scripts/watch_prd8_live_match.py` already uses.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import socket
import threading
import time

import pytest

from cop.domain.scoring import Outcome, Score
from cop.integrity.hardware_declaration import HardwareDeclaration
from cop.integrity.step0 import Step0Declaration
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


def _opponent_declaration(**overrides) -> Step0Declaration:
    defaults = {
        "hardware": HardwareDeclaration(
            os_name="Linux", cpu_cores=8, ram_gb=16.0, gpu_present=False, gpu_vram_gb=None,
            llm_model="test-model",
        ),
        "code_commit_hash": "b" * 40,
        "group_name": "team-b",
        "sub_game_number": 1,
        "config_sha256": "c" * 64,
        "scent_model_sha256": "d" * 64,
    }
    defaults.update(overrides)
    return Step0Declaration(**defaults)


_NUM_SUB_GAMES = 6  # Table 18 row 3 — FIXED (PARAMETERS.md)


def _client(config, tmp_path, name: str = "client", *, sub_game_number: int = 1) -> Orchestrator:
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / f"{name}_trace.jsonl"))
    if sub_game_number != 1:
        client.private_config = dataclasses.replace(client.private_config, sub_game_number=sub_game_number)
    client.league_ledger = client.league_ledger.__class__(path=str(tmp_path / f"{name}_ledger.json"))
    client._opponent_declaration = _opponent_declaration(sub_game_number=sub_game_number)
    return client


def _final_sub_game_client(config, tmp_path, name: str = "client") -> Orchestrator:
    """`report_game()` only sends once `sub_game_number == num_sub_games`
    (PRD 16, ch. 9.4: one report for the whole series) — most of this
    file's own per-call assertions need that last sub-game to actually
    reach the Gatekeeper/email send."""
    return _client(config, tmp_path, name, sub_game_number=_NUM_SUB_GAMES)


def _report_game(client, peer_url, *, is_counted: bool):
    return asyncio.run(
        client.report_game(
            peer_url,
            Outcome.SURVIVAL,
            is_counted,
            opponent_id=peer_url,
            score=Score(cop=5, thief=10),
            opponent_cop_repo_url="https://github.com/team-b/cop",
            opponent_thief_repo_url="https://github.com/team-b/thief",
        )
    )


def test_report_game_returns_cleanly_under_draft_mode(config, tmp_path):
    client = _final_sub_game_client(config, tmp_path)  # else None means "not yet final", not "draft"
    peer_url = _start_peer(config, tmp_path)

    result = _report_game(client, peer_url, is_counted=True)

    assert result is None  # config/game.toml's own email_mode is "draft"


def test_report_game_records_a_counted_game_when_is_counted_true(config, tmp_path):
    client = _client(config, tmp_path)
    peer_url = _start_peer(config, tmp_path)

    _report_game(client, peer_url, is_counted=True)

    assert client.league_ledger.counted_game_count() == 1
    assert client.league_ledger.is_already_counted(peer_url)


def test_report_game_does_not_record_a_warm_up_game(config, tmp_path):
    client = _client(config, tmp_path)
    peer_url = _start_peer(config, tmp_path)

    _report_game(client, peer_url, is_counted=False)

    assert client.league_ledger.counted_game_count() == 0


def test_report_game_calls_each_step_in_the_documented_order(config, tmp_path):
    client = _final_sub_game_client(config, tmp_path)  # gatekeeper_execute only fires on the last sub-game
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


def test_report_game_writes_repo_urls_from_a_completed_negotiation(config, tmp_path):
    client = _client(config, tmp_path)
    peer_url = _start_peer(config, tmp_path)
    client._opponent_repos = {
        "cop": "https://github.com/team-b/cop", "thief": "https://github.com/team-b/thief",
    }

    asyncio.run(
        client.report_game(
            peer_url, Outcome.SURVIVAL, is_counted=True, opponent_id=peer_url, score=Score(cop=5, thief=10)
        )
    )

    game_id = client.private_config.group_id
    result_path = tmp_path / f"result_{game_id}.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    this_group = client.private_config.group_name
    assert result["repo_urls"][this_group + "_cop"] == client.private_config.repos["cop"]
    assert result["repo_urls"]["team-b_cop"] == "https://github.com/team-b/cop"
    assert result["repo_urls"]["team-b_thief"] == "https://github.com/team-b/thief"


def test_report_game_explicit_override_wins_over_a_completed_negotiation(config, tmp_path):
    client = _client(config, tmp_path)
    peer_url = _start_peer(config, tmp_path)
    client._opponent_repos = {
        "cop": "https://github.com/from-negotiation/cop", "thief": "https://github.com/from-negotiation/thief",
    }

    asyncio.run(
        client.report_game(
            peer_url,
            Outcome.SURVIVAL,
            is_counted=True,
            opponent_id=peer_url,
            score=Score(cop=5, thief=10),
            opponent_cop_repo_url="https://github.com/explicit/cop",
            opponent_thief_repo_url="https://github.com/explicit/thief",
        )
    )

    game_id = client.private_config.group_id
    result = json.loads((tmp_path / f"result_{game_id}.json").read_text(encoding="utf-8"))
    assert result["repo_urls"]["team-b_cop"] == "https://github.com/explicit/cop"
    assert result["repo_urls"]["team-b_thief"] == "https://github.com/explicit/thief"


def test_report_game_attaches_all_four_table_20_files(config, tmp_path, monkeypatch):
    client = _final_sub_game_client(config, tmp_path)  # attachments only exist on the last sub-game
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

    result_payload = attachments[f"result_{game_id}.json"]
    assert result_payload["sub_games"][0]["sub_game_number"] == sub_game_number
    assert "mutual_agreement" in result_payload

    # Every attachment round-trips through JSON cleanly (rule 34: JSON, not free text).
    for payload in attachments.values():
        assert json.loads(json.dumps(payload)) == payload

    # And the same result content genuinely landed on disk, not just in the email.
    on_disk = json.loads((tmp_path / f"result_{game_id}.json").read_text(encoding="utf-8"))
    assert on_disk == result_payload


def test_report_game_does_not_send_before_the_series_final_sub_game(config, tmp_path, monkeypatch):
    # PRD 16's own correction: ch. 9.4's result report is for the whole
    # series, sent once — a non-final sub-game must persist its own merge
    # to disk (proving accumulation still works) but never reach the
    # Gatekeeper/email send.
    client = _client(config, tmp_path, sub_game_number=1)  # 1 of 6 — not the last
    peer_url = _start_peer(config, tmp_path)
    client._opponent_repos = {
        "cop": "https://github.com/team-b/cop", "thief": "https://github.com/team-b/thief",
    }

    execute_calls = []
    monkeypatch.setattr(
        client.gatekeeper, "execute", lambda *a, **kw: execute_calls.append((a, kw))
    )

    result = asyncio.run(
        client.report_game(
            peer_url, Outcome.SURVIVAL, is_counted=True, opponent_id=peer_url, score=Score(cop=5, thief=10)
        )
    )

    assert result is None
    assert execute_calls == []  # never reached the Gatekeeper at all

    game_id = client.private_config.group_id
    on_disk = json.loads((tmp_path / f"result_{game_id}.json").read_text(encoding="utf-8"))
    assert len(on_disk["sub_games"]) == 1  # the merge itself still happened
    assert on_disk["sub_games"][0]["sub_game_number"] == 1


def test_report_game_raises_when_neither_override_nor_negotiation_is_available(config, tmp_path):
    client = _client(config, tmp_path)
    peer_url = _start_peer(config, tmp_path)
    assert client._opponent_repos is None

    with pytest.raises(ValueError, match="opponent_cop_repo_url"):
        asyncio.run(
            client.report_game(
                peer_url, Outcome.SURVIVAL, is_counted=True, opponent_id=peer_url, score=Score(cop=5, thief=10)
            )
        )


def test_report_game_raises_when_opponent_declaration_is_missing(config, tmp_path):
    # Distinct rejection path from the repo-url one above: real repos but no
    # retained Step-0 declaration (group_name/code_commit_hash have no
    # other honest source, PRD 16).
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.league_ledger = client.league_ledger.__class__(path=str(tmp_path / "ledger.json"))
    peer_url = _start_peer(config, tmp_path)
    assert client._opponent_declaration is None

    with pytest.raises(ValueError, match="_opponent_declaration"):
        asyncio.run(
            client.report_game(
                peer_url,
                Outcome.SURVIVAL,
                is_counted=True,
                opponent_id=peer_url,
                score=Score(cop=5, thief=10),
                opponent_cop_repo_url="https://github.com/team-b/cop",
                opponent_thief_repo_url="https://github.com/team-b/thief",
            )
        )


def test_two_sequential_real_sub_games_genuinely_accumulate_not_overwrite(config, tmp_path):
    # PRD 16's own real gap: a real series spans six separate Orchestrator
    # process lifetimes (PRD 10), one per sub-game — this constructs two,
    # sequentially, against the *same* tmp_path/game_id, matching that shape
    # exactly (not one Orchestrator calling report_game twice).
    #
    # Distinct opponent_id per call, deliberately: league_ledger.py's own
    # rule 52 enforcement is "one counted game per opponent_id", a
    # per-*series* concept unrelated to what this test verifies (the
    # per-sub-game result-file accumulation, keyed by game_id/sub_game_number,
    # never by opponent_id). A real caller would pass the same opponent_id
    # across a whole series and set is_counted accordingly; that's
    # league_ledger's own, separately-tested concern, not this one's.
    first_client = _client(config, tmp_path, name="sub_game_1")
    first_client._opponent_repos = {
        "cop": "https://github.com/team-b/cop", "thief": "https://github.com/team-b/thief",
    }
    game_id = first_client.private_config.group_id
    peer_url_1 = _start_peer(config, tmp_path)
    asyncio.run(
        first_client.report_game(
            peer_url_1,
            Outcome.CAPTURE,
            is_counted=True,
            opponent_id="team-b-game1",
            score=Score(cop=20, thief=5),
        )
    )

    second_private_config = dataclasses.replace(first_client.private_config, sub_game_number=2)
    second_client = Orchestrator(
        config, CopBrain(), log_path=str(tmp_path / "sub_game_2_trace.jsonl"), private_config=second_private_config
    )
    second_client.league_ledger = first_client.league_ledger.__class__(
        path=str(tmp_path / "sub_game_1_ledger.json")
    )
    second_client._opponent_declaration = _opponent_declaration(sub_game_number=2)
    second_client._opponent_repos = dict(first_client._opponent_repos)
    peer_url_2 = _start_peer(config, tmp_path)
    asyncio.run(
        second_client.report_game(
            peer_url_2,
            Outcome.SURVIVAL,
            is_counted=True,
            opponent_id="team-b-game2",
            score=Score(cop=5, thief=10),
        )
    )

    result = json.loads((tmp_path / f"result_{game_id}.json").read_text(encoding="utf-8"))
    this_group = first_client.private_config.group_name
    assert [g["sub_game_number"] for g in result["sub_games"]] == [1, 2]
    assert result["final_result"]["total_score"][this_group] == 25  # 20 + 5, not just the second call's 5
    assert result["final_result"]["sub_games_won"] == 1  # only the capture sub-game
    assert result["game_uid"]  # same series identity preserved across both real calls
