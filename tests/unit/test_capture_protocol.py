"""Rules 21/22 (**[FATAL]**): a capture claim must be truthfully answerable
— accept path and reject path both tested, matching this project's own
"write at least one test per layer that proves rejection" rule.
"""

from __future__ import annotations

from cop.domain.board import Position
from cop.integrity.capture_protocol import claim_capture, respond_to_capture_claim


def test_matching_positions_confirm_the_claim():
    claim = claim_capture(thief_pos=Position(3, 3), cop_pos=Position(3, 3), claimed_at_step=5)
    response = respond_to_capture_claim(claim, true_thief_pos=Position(3, 3))
    assert response.confirmed is True
    assert response.true_thief_pos == Position(3, 3)


def test_mismatched_positions_reject_the_claim():
    """The reject path the old xfail guard never had room to write — it
    only ever tested the accept scenario."""
    claim = claim_capture(thief_pos=Position(3, 3), cop_pos=Position(3, 3))
    response = respond_to_capture_claim(claim, true_thief_pos=Position(5, 1))
    assert response.confirmed is False
    assert response.true_thief_pos == Position(5, 1)


def test_claim_capture_defaults_claimed_at_step_to_zero():
    claim = claim_capture(thief_pos=Position(1, 1), cop_pos=Position(1, 1))
    assert claim.claimed_at_step == 0
