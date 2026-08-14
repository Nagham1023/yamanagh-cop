"""`BeliefMap.update_from_hint`/`_focal_region` — split out of `belief.py`
once it re-hit the 150-line cap adding `update_from_scent`'s negative-
probability fix. Hint-specific: the scent-side updates
(`update_from_scent`/`update_from_scent_map`) stay in `belief.py`, same
"split by concern, not just by size" precedent `belief_queries.py`'s own
read/write split already set.
"""

from __future__ import annotations

from ..domain.board import Board, Position
from ..domain.movement import DELTAS

_HINT_RELIABILITY = 0.6


class BeliefHintUpdateMixin:
    """Expects `self._probabilities: dict[Position, float]` and
    `self._normalize()` — `BeliefMap`'s own fields/method, per the dataclass
    this mixin is combined with."""

    def _focal_region(self, focal_point: Position, board: Board) -> set[Position]:
        cells = {focal_point}
        for direction, delta in DELTAS.items():
            if direction == "STAY":
                continue
            neighbour = focal_point + delta
            if board.in_bounds(neighbour):
                cells.add(neighbour)
        return cells

    def update_from_hint(self, focal_point: Position, board: Board) -> None:
        """`P(state|evidence) ∝ P(evidence|state)·P(state)` — the focal
        region gets likelihood `_HINT_RELIABILITY`, every other tracked
        cell gets `(1-_HINT_RELIABILITY)/N`. `focal_point` comes from
        `reasoning.hint.interpret_hint` — this method doesn't know or care
        whether it's honest or a lie; corroboration against the always-
        truthful scent map (`update_from_scent_map`) is what protects
        against that, not this method itself."""
        focal_cells = self._focal_region(focal_point, board)
        tracked = set(self._probabilities)
        elsewhere = tracked - focal_cells
        # _HINT_RELIABILITY is the region's *total* likelihood mass, split
        # evenly across its cells — not applied to each cell independently
        # (that would over-count the evidence once per cell in the region).
        focal_likelihood = _HINT_RELIABILITY / len(focal_cells) if focal_cells else 0.0
        elsewhere_likelihood = (1 - _HINT_RELIABILITY) / len(elsewhere) if elsewhere else 0.0
        for cell in tracked:
            likelihood = focal_likelihood if cell in focal_cells else elsewhere_likelihood
            self._probabilities[cell] *= likelihood
        self._normalize()
