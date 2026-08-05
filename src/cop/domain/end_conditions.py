"""End-of-subgame determination: turns capture/step-count signals into one Outcome.

This module owns no state — PRD 2's turn loop will call `determine_outcome`
once per turn with whatever capture check already ran and the current step
count. It never touches the board or barriers directly, so it stays testable
with plain booleans and integers.
"""

from __future__ import annotations

from .scoring import Outcome


def determine_outcome(
    *,
    captured: bool,
    steps_taken: int,
    step_ceiling: int,
    survival_threshold: int,
) -> Outcome | None:
    """Return the sub-game's Outcome, or None if it is still in progress.

    Capture is checked first: even on the exact step the ceiling or survival
    threshold is reached, a captured thief scores as CAPTURE, not SURVIVAL —
    rules 46/47 exist precisely to end the game the instant they trigger,
    taking precedence over any step-count condition evaluated the same turn.
    """
    if captured:
        return Outcome.CAPTURE
    if steps_taken >= survival_threshold or steps_taken >= step_ceiling:
        return Outcome.SURVIVAL
    return None
