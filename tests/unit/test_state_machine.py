"""State machine (rules 4, 5): every legal transition succeeds, everything else is rejected."""

from __future__ import annotations

import pytest

from cop.planner.state_machine import PeerStateMachine


def test_starts_waiting_for_opponent():
    machine = PeerStateMachine()
    assert machine.state == "WAITING_FOR_OPPONENT"


def test_full_round_trip_cycle_is_legal():
    machine = PeerStateMachine()
    assert machine.transition("SENDING") == "SENDING"
    assert machine.transition("AWAITING_RESPONSE") == "AWAITING_RESPONSE"
    assert machine.transition("TURN_RESOLVED") == "TURN_RESOLVED"
    assert machine.transition("WAITING_FOR_OPPONENT") == "WAITING_FOR_OPPONENT"


@pytest.mark.parametrize("state", ["WAITING_FOR_OPPONENT", "SENDING", "AWAITING_RESPONSE", "TURN_RESOLVED"])
def test_technical_loss_reachable_from_every_non_terminal_state(state):
    machine = PeerStateMachine(state=state)
    assert machine.transition("TECHNICAL_LOSS") == "TECHNICAL_LOSS"


def test_technical_loss_is_terminal():
    machine = PeerStateMachine(state="TECHNICAL_LOSS")
    with pytest.raises(ValueError, match="Illegal transition"):
        machine.transition("WAITING_FOR_OPPONENT")


def test_skipping_a_state_is_rejected():
    machine = PeerStateMachine()
    with pytest.raises(ValueError, match="Illegal transition"):
        machine.transition("TURN_RESOLVED")
    # rejection must not silently move the state anyway
    assert machine.state == "WAITING_FOR_OPPONENT"


def test_unknown_target_state_is_rejected():
    machine = PeerStateMachine()
    with pytest.raises(ValueError, match="Illegal transition"):
        machine.transition("NOT_A_REAL_STATE")


def test_a_machine_constructed_in_an_unknown_state_rejects_any_transition():
    # PeerStateMachine's `state` field has no constructor-time validation,
    # so a directly-constructed garbage state is possible — this proves the
    # transition() guard against it, not just against bad transition targets.
    machine = PeerStateMachine(state="NOT_A_REAL_STATE")
    with pytest.raises(ValueError, match="Unknown current state"):
        machine.transition("WAITING_FOR_OPPONENT")
