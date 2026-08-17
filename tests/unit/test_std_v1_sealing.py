"""std_v1/sealing.py tests — the turn message never carries `move`
(spec Section 9); only the audit record does."""

from __future__ import annotations

from cop.std_v1.sealing import (
    build_audit_record,
    build_turn_message,
    build_turn_payload,
    seal_turn,
    verify_record,
)


def test_build_turn_message_never_leaks_the_move():
    payload = build_turn_payload(step=2, sender="police", move="N", hint="", smell_grid={})
    sealed = seal_turn(payload)
    message = build_turn_message(payload, sealed["commit"])
    assert "move" not in message
    assert message["commit"] == sealed["commit"]
    assert message["step"] == 2


def test_build_turn_message_carries_every_public_field():
    payload = build_turn_payload(
        step=4, sender="police", move="E", hint="warm", smell_grid={"1,1": 0.5},
        barrier_placed=[2, 2], capture_claim=[1, 1],
    )
    sealed = seal_turn(payload)
    message = build_turn_message(payload, sealed["commit"])
    assert message["barrier_placed"] == [2, 2]
    assert message["capture_claim"] == [1, 1]
    assert message["smell_grid"] == {"1,1": 0.5}


def test_seal_and_verify_round_trip_succeeds_untampered():
    payload = build_turn_payload(step=2, sender="police", move="N", hint="", smell_grid={})
    sealed = seal_turn(payload)
    record = build_audit_record(payload, sealed["nonce"])
    assert verify_record(record, sealed["commit"]) is True


def test_verify_record_fails_on_a_tampered_move():
    payload = build_turn_payload(step=2, sender="police", move="N", hint="", smell_grid={})
    sealed = seal_turn(payload)
    record = build_audit_record(payload, sealed["nonce"])
    record["move"] = "S"
    assert verify_record(record, sealed["commit"]) is False


def test_verify_record_fails_on_a_wrong_nonce():
    payload = build_turn_payload(step=2, sender="police", move="N", hint="", smell_grid={})
    sealed = seal_turn(payload)
    record = build_audit_record(payload, "0" * 32)
    assert verify_record(record, sealed["commit"]) is False


def test_seal_turn_produces_a_fresh_nonce_each_call():
    payload = build_turn_payload(step=2, sender="police", move="N", hint="", smell_grid={})
    first = seal_turn(payload)
    second = seal_turn(payload)
    assert first["nonce"] != second["nonce"]
    assert first["commit"] != second["commit"]


def test_build_audit_record_carries_the_hidden_move_field():
    payload = build_turn_payload(step=2, sender="police", move="W", hint="", smell_grid={})
    record = build_audit_record(payload, "n" * 32)
    assert record["move"] == "W"
    assert record["nonce"] == "n" * 32
