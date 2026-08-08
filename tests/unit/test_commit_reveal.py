"""PRD 6's `commit()`/`verify()` (ch. 5.3.1, p.53) — every field must be
load-bearing in the hash, and `verify()` must reject anything tampered
after the fact. "A verifier that never rejects anything is worthless"
(CLAUDE.md's own house rule) — most of this file is rejection tests, not
acceptance ones.
"""

from __future__ import annotations

import secrets
from dataclasses import replace

import pytest

from cop.domain.board import Position
from cop.integrity.commit_reveal import CommitEnvelope, commit, move_to_wire, verify, wire_to_action
from cop.reasoning.brain_base import Move, PlaceBarrier

_STATE = b'{"barriers_placed":[],"own_pos":[2,2],"steps_taken":3}'


def _envelope(**overrides) -> CommitEnvelope:
    base = {
        "state": _STATE,
        "move": {"type": "move", "direction": "NORTH"},
        "intent": False,
        "nonce": "a" * 32,
        "hint_text": "quiet by the river",
        "step": 3,
        "role": "cop",
    }
    base.update(overrides)
    return CommitEnvelope(**base)


def test_move_to_wire_serializes_a_move():
    assert move_to_wire(Move(direction="NORTH")) == {"type": "move", "direction": "NORTH"}


def test_move_to_wire_serializes_a_barrier_placement():
    assert move_to_wire(PlaceBarrier(target=Position(4, 5))) == {
        "type": "place_barrier",
        "col": 4,
        "row": 5,
    }


def test_commit_is_deterministic_for_the_same_logical_envelope():
    assert commit(_envelope()) == commit(_envelope())


@pytest.mark.parametrize(
    "overrides",
    [
        {"state": b'{"barriers_placed":[],"own_pos":[9,9],"steps_taken":3}'},
        {"move": {"type": "move", "direction": "SOUTH"}},
        {"intent": True},
        {"nonce": "b" * 32},
        {"hint_text": "a different sentence"},
        {"step": 4},
        {"role": "thief"},
    ],
)
def test_changing_any_single_field_changes_the_commit_hash(overrides):
    assert commit(_envelope()) != commit(_envelope(**overrides))


def test_verify_accepts_a_genuine_pair():
    envelope = _envelope()
    assert verify(envelope, commit(envelope)) is True


def test_verify_rejects_a_tampered_envelope():
    envelope = _envelope()
    h_commit = commit(envelope)
    tampered = replace(envelope, hint_text="a lie inserted after commit")
    assert verify(tampered, h_commit) is False


def test_verify_uses_compare_digest_not_equality(monkeypatch):
    """Code-inspection-backed, not just behavioral: confirm the actual
    primitive used is `secrets.compare_digest`, since a plain `==` would
    pass every behavioral test above just as well but reintroduce the
    timing side-channel `verify()`'s docstring specifically rules out."""
    calls = []
    real_compare_digest = secrets.compare_digest

    def _spy(a, b):
        calls.append((a, b))
        return real_compare_digest(a, b)

    monkeypatch.setattr("cop.integrity.commit_reveal.secrets.compare_digest", _spy)
    envelope = _envelope()
    verify(envelope, commit(envelope))
    assert len(calls) == 1


def test_wire_to_action_is_the_true_inverse_of_move_to_wire():
    assert wire_to_action(move_to_wire(Move(direction="NORTH"))) == Move(direction="NORTH")
    assert wire_to_action(move_to_wire(PlaceBarrier(target=Position(4, 5)))) == PlaceBarrier(
        target=Position(4, 5)
    )


@pytest.mark.parametrize(
    "malformed",
    [
        {"type": "move"},  # missing direction
        {"type": "move", "direction": 5},  # wrong type
        {"type": "place_barrier", "col": "not-an-int", "row": 1},
        {"type": "place_barrier", "row": 1},  # missing col
        {"type": "levitate"},  # unrecognized type
        {},  # no type at all
    ],
)
def test_wire_to_action_rejects_malformed_input(malformed):
    with pytest.raises(ValueError):
        wire_to_action(malformed)
