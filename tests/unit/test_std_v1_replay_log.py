"""std_v1/replay_log.py tests (rule 20 **[FATAL]**) — a verifier that has
never rejected anything is indistinguishable from a broken one, so the
tamper case here is as load-bearing as the clean-pass case."""

from __future__ import annotations

import json

from cop.std_v1.replay_log import is_std_v1_log, merge_records, verify_sub_game_log, write_sub_game_log
from cop.std_v1.sealing import build_audit_record, build_turn_payload, seal_turn


def _sealed_record(step: int, sender: str) -> tuple[dict, str]:
    payload = build_turn_payload(step=step, sender=sender, move="N", hint="", smell_grid={})
    sealed = seal_turn(payload)
    return build_audit_record(payload, sealed["nonce"]), sealed["commit"]


def test_merge_records_combines_both_sides_in_step_order():
    my_record, my_commit = _sealed_record(2, "police")
    peer_record, peer_commit = _sealed_record(1, "thief")

    merged = merge_records([my_record], {2: my_commit}, [peer_record], {1: peer_commit})

    assert [r["step"] for r in merged] == [1, 2]
    assert merged[0]["live_commit"] == peer_commit
    assert merged[1]["live_commit"] == my_commit


def test_write_then_verify_a_clean_log_reports_every_step_ok(tmp_path):
    my_record, my_commit = _sealed_record(2, "police")
    peer_record, peer_commit = _sealed_record(1, "thief")
    merged = merge_records([my_record], {2: my_commit}, [peer_record], {1: peer_commit})

    log_path = write_sub_game_log("dev-team-vs-thief-team", 1, merged, tmp_path)

    assert log_path.name == "log_dev-team-vs-thief-team_g01.json"
    assert is_std_v1_log(log_path)
    result = verify_sub_game_log(log_path)
    assert result["passed"] is True
    assert all(step["verified"] for step in result["steps"])


def test_verify_sub_game_log_rejects_a_tampered_record(tmp_path):
    my_record, my_commit = _sealed_record(2, "police")
    merged = merge_records([my_record], {2: my_commit}, [], {})
    log_path = write_sub_game_log("dev-team-vs-thief-team", 1, merged, tmp_path)

    data = json.loads(log_path.read_text(encoding="utf-8"))
    data["records"][0]["move"] = "TAMPERED"
    log_path.write_text(json.dumps(data), encoding="utf-8")

    result = verify_sub_game_log(log_path)
    assert result["passed"] is False
    assert result["steps"][0]["verified"] is False


def test_is_std_v1_log_rejects_native_jsonl_format(tmp_path):
    native_log = tmp_path / "log_native.json"
    native_log.write_text('{"event": "committing", "step": 1}\n{"event": "revealed", "step": 1}\n')

    assert is_std_v1_log(native_log) is False
