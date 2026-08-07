"""Rules 21/22 (both **[FATAL]**): the cop declares a capture, the thief is
cryptographically obliged to answer truthfully. `domain/capture.py`
detects a capture locally; this module is the declaration channel that
carries that fact to the peer, with the exact `claim_capture`/
`respond_to_capture_claim` API `tests/unit/test_capture_protocol.py` tests.

This repo is the cop — in practice, this side only ever *sends*
`CaptureClaim`s (built from `domain/capture.py`'s own already-true local
predicates, `is_coordinate_capture`/`is_barrier_capture`) and *receives*
`CaptureResponse`s from the thief peer, since only the thief knows its own
real position well enough to truthfully confirm or deny one. Both
directions are built and tested here regardless — rules 21/22 are
symmetric, and the thief-repo's own equivalent module is what actually
calls `respond_to_capture_claim` for real. Rule 21/22 enforcement itself
isn't a separate, weaker mechanism than moves get: both the claim and the
response fold into that side's own next commit envelope
(`commit_reveal.CommitEnvelope`), checked like everything else at final
audit (`integrity/audit.py`).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.board import Position


@dataclass(frozen=True)
class CaptureClaim:
    thief_pos: Position
    cop_pos: Position
    claimed_at_step: int


@dataclass(frozen=True)
class CaptureResponse:
    confirmed: bool
    true_thief_pos: Position


def claim_capture(thief_pos: Position, cop_pos: Position, claimed_at_step: int = 0) -> CaptureClaim:
    """Pure, local, honest-by-construction: this repo only ever calls this
    when `domain/capture.py`'s own `is_coordinate_capture`/
    `is_barrier_capture` already returned `True` locally — this function
    doesn't re-derive that, it just packages an already-true local fact for
    the wire."""
    return CaptureClaim(thief_pos=thief_pos, cop_pos=cop_pos, claimed_at_step=claimed_at_step)


def respond_to_capture_claim(claim: CaptureClaim, true_thief_pos: Position) -> CaptureResponse:
    """Called on data *this repo receives from the peer* — the responder is
    the side that actually knows `true_thief_pos`, which for a claim this
    repo (the cop) makes is the thief. Built and tested on both sides of the
    exchange since the guard test exercises both, even though only the
    claim-sending direction is this repo's own live call path."""
    return CaptureResponse(
        confirmed=claim.thief_pos == true_thief_pos, true_thief_pos=true_thief_pos
    )
