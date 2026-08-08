"""State machine (rules 4, 5): every legal transition succeeds, everything
else is rejected. Matches the book's own Ch.8 Fig. 11 table (p.80) plus one
argued extra edge (`COMMITTING -> TECHNICAL_LOSS`) — see the module
docstring for the full citation and argument.
"""

from __future__ import annotations

import pytest

from cop.planner.state_machine import PeerStateMachine


def test_starts_waiting_for_opponent():
    machine = PeerStateMachine()
    assert machine.state == "WAITING_FOR_OPPONENT"


def test_full_round_trip_cycle_is_legal():
    machine = PeerStateMachine()
    assert machine.transition("COMPUTING_MOVE") == "COMPUTING_MOVE"
    assert machine.transition("COMMITTING") == "COMMITTING"
    assert machine.transition("AWAITING_REVEAL") == "AWAITING_REVEAL"
    assert machine.transition("VERIFYING") == "VERIFYING"
    assert machine.transition("WAITING_FOR_OPPONENT") == "WAITING_FOR_OPPONENT"


@pytest.mark.parametrize("state", ["COMPUTING_MOVE", "COMMITTING", "AWAITING_REVEAL"])
def test_technical_loss_reachable_from_the_books_own_two_states_plus_committing(state):
    machine = PeerStateMachine(state=state)
    assert machine.transition("TECHNICAL_LOSS") == "TECHNICAL_LOSS"


@pytest.mark.parametrize("state", ["WAITING_FOR_OPPONENT", "VERIFYING"])
def test_technical_loss_is_not_reachable_from_states_with_no_pending_peer_response(state):
    """The narrower, argued position (PRD 6 Design Question 4): only states
    representing an active wait on a pending peer response get the edge —
    `WAITING_FOR_OPPONENT` (idle between turns) and `VERIFYING` (the reveal
    is already in hand, purely local) do not, matching the book's own
    literal table exactly."""
    machine = PeerStateMachine(state=state)
    with pytest.raises(ValueError, match="Illegal transition"):
        machine.transition("TECHNICAL_LOSS")


def test_committing_directly_from_waiting_is_rejected_now_that_computing_move_exists():
    # The old PRD 2 shortcut — legal before PRD 3 gave COMPUTING_MOVE
    # something real to represent, illegal now that it does.
    machine = PeerStateMachine()
    with pytest.raises(ValueError, match="Illegal transition"):
        machine.transition("COMMITTING")
    assert machine.state == "WAITING_FOR_OPPONENT"


def test_technical_loss_is_terminal():
    machine = PeerStateMachine(state="TECHNICAL_LOSS")
    with pytest.raises(ValueError, match="Illegal transition"):
        machine.transition("WAITING_FOR_OPPONENT")


def test_skipping_a_state_is_rejected():
    machine = PeerStateMachine()
    with pytest.raises(ValueError, match="Illegal transition"):
        machine.transition("VERIFYING")
    # rejection must not silently move the state anyway
    assert machine.state == "WAITING_FOR_OPPONENT"


def test_unknown_target_state_is_rejected():
    machine = PeerStateMachine()
    with pytest.raises(ValueError, match="Illegal transition"):
        machine.transition("NOT_A_REAL_STATE")


def test_negotiating_reaches_waiting_for_opponent_on_a_verified_match():
    machine = PeerStateMachine(state="NEGOTIATING")
    assert machine.transition("WAITING_FOR_OPPONENT") == "WAITING_FOR_OPPONENT"


def test_negotiating_reaches_technical_loss_on_a_mismatch():
    machine = PeerStateMachine(state="NEGOTIATING")
    assert machine.transition("TECHNICAL_LOSS") == "TECHNICAL_LOSS"


def test_negotiating_cannot_skip_straight_into_the_per_turn_cycle():
    machine = PeerStateMachine(state="NEGOTIATING")
    with pytest.raises(ValueError, match="Illegal transition"):
        machine.transition("COMMITTING")
    assert machine.state == "NEGOTIATING"


def test_a_machine_constructed_in_an_unknown_state_rejects_any_transition():
    # PeerStateMachine's `state` field has no constructor-time validation,
    # so a directly-constructed garbage state is possible — this proves the
    # transition() guard against it, not just against bad transition targets.
    machine = PeerStateMachine(state="NOT_A_REAL_STATE")
    with pytest.raises(ValueError, match="Unknown current state"):
        machine.transition("WAITING_FOR_OPPONENT")
