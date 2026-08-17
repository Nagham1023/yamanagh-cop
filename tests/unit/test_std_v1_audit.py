"""std_v1/audit.py tests (spec Sections 9-11)."""

from __future__ import annotations

import asyncio

import pytest

from cop.planner.deadline import DeadlineExceededError
from cop.std_v1.audit import (
    build_audit_envelope,
    build_consensus_envelope,
    build_consensus_object,
    build_sub_game_row,
    confirm_agreement,
    send_and_await,
    validate_consensus_envelope,
    verify_peer_records,
)
from cop.std_v1.exchange import StdExchange
from cop.std_v1.sealing import build_audit_record, build_turn_payload, seal_turn


def test_verify_peer_records_passes_for_untampered_data():
    payload = build_turn_payload(step=1, sender="thief", move="N", hint="", smell_grid={})
    sealed = seal_turn(payload)
    record = build_audit_record(payload, sealed["nonce"])

    result = verify_peer_records([record], peer_commits={1: sealed["commit"]})

    assert result["log_verified"] is True
    assert result["tampered"] is False
    assert result["mismatched_steps"] == []


def test_verify_peer_records_catches_a_tampered_move():
    payload = build_turn_payload(step=1, sender="thief", move="N", hint="", smell_grid={})
    sealed = seal_turn(payload)
    tampered_record = build_audit_record({**payload, "move": "S"}, sealed["nonce"])

    result = verify_peer_records([tampered_record], peer_commits={1: sealed["commit"]})

    assert result["log_verified"] is False
    assert result["tampered"] is True
    assert result["mismatched_steps"] == [1]


def test_verify_peer_records_catches_a_record_for_a_step_never_seen_live():
    payload = build_turn_payload(step=99, sender="thief", move="N", hint="", smell_grid={})
    sealed = seal_turn(payload)
    record = build_audit_record(payload, sealed["nonce"])

    result = verify_peer_records([record], peer_commits={})

    assert result["tampered"] is True
    assert result["mismatched_steps"] == [99]


def test_build_sub_game_row_has_exactly_five_keys():
    row = build_sub_game_row(1, "capture", {"a": "police", "b": "thief"}, {"a": 1, "b": 0}, "a")
    assert set(row) == {"sub_game_number", "result", "roles", "score", "winner_group"}


def test_build_consensus_object_sorts_rows_by_sub_game_number():
    rows = [
        build_sub_game_row(3, "survival", {}, {}, None),
        build_sub_game_row(1, "capture", {}, {}, "a"),
        build_sub_game_row(2, "timeout", {}, {}, None),
    ]
    obj = build_consensus_object("a-vs-b", "uid", rows)
    assert [row["sub_game_number"] for row in obj["sub_games"]] == [1, 2, 3]
    assert set(obj) == {"game_id", "game_uid", "sub_games"}


def test_validate_consensus_envelope_accepts_a_well_formed_one():
    envelope = build_consensus_envelope("police", "a" * 64)
    assert validate_consensus_envelope(envelope) == "a" * 64


def test_validate_consensus_envelope_rejects_wrong_result_claim():
    envelope = build_consensus_envelope("police", "a" * 64)
    envelope["result_claim"] = "capture"
    with pytest.raises(ValueError, match="result_claim"):
        validate_consensus_envelope(envelope)


def test_validate_consensus_envelope_rejects_non_empty_records():
    envelope = build_consensus_envelope("police", "a" * 64)
    envelope["records"] = [{"step": 1}]
    with pytest.raises(ValueError, match="records"):
        validate_consensus_envelope(envelope)


def test_validate_consensus_envelope_rejects_a_short_digest():
    envelope = build_consensus_envelope("police", "abc")
    with pytest.raises(ValueError, match="consensus_sha"):
        validate_consensus_envelope(envelope)


def test_validate_consensus_envelope_rejects_a_non_wire_role_sender():
    envelope = build_consensus_envelope("dev-team", "a" * 64)
    with pytest.raises(ValueError, match="wire role"):
        validate_consensus_envelope(envelope)


def test_confirm_agreement_requires_all_three_conditions():
    assert confirm_agreement(True, True, "x", "x") is True
    assert confirm_agreement(False, True, "x", "x") is False
    assert confirm_agreement(True, False, "x", "x") is False
    assert confirm_agreement(True, True, "x", "y") is False


class _Connection:
    async def call_tool(self, name, arguments):
        class _Result:
            data = {"ok": True}

        return _Result()


def test_send_and_await_returns_once_the_peer_responds():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_audit({"sub_game_number": 1, "result_claim": "capture"})
    envelope = build_audit_envelope("police", [], "capture", 1)

    result = asyncio.run(send_and_await(
        _Connection(), lambda timeout: exchange.wait_for_audit(1, timeout),
        envelope, resend_interval_sec=0.05, ceiling_sec=2.0,
    ))

    assert result["result_claim"] == "capture"


def test_send_and_await_times_out_when_the_peer_never_responds():
    exchange = StdExchange(poll_interval=0.01)
    envelope = build_audit_envelope("police", [], "capture", 1)

    with pytest.raises(DeadlineExceededError):
        asyncio.run(send_and_await(
            _Connection(), lambda timeout: exchange.wait_for_audit(1, timeout),
            envelope, resend_interval_sec=0.05, ceiling_sec=0.2,
        ))


def test_build_audit_envelope_carries_all_four_fields():
    envelope = build_audit_envelope("police", [{"step": 2}], "capture", 3)
    assert envelope == {"sender": "police", "records": [{"step": 2}], "result_claim": "capture", "sub_game_number": 3}
