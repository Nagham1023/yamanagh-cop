"""Bayesian-flavoured belief heatmap over where the thief is (PRD 4 Design
Question 2): a genuine probability distribution, always renormalized to 1.

Update math, decided and documented here rather than left implicit: both
updates are multiplicative down/up-weighting followed by renormalization —
a simpler weighted-reweighting scheme than a full Bayesian posterior, which
is defensible for this layer (the milestone needs a measurable, correctly-
directioned shift, not an optimal estimator). `update_from_scent` down-
weights cells the cop has itself recently searched (fresh scent = less
likely the thief is there); `update_from_hint` up-weights the interpreted
hint's focal region. Neither can ever zero out a cell's probability
entirely (down-weight factors are always > 0), so renormalization never
divides by zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.board import Board, Position
from ..domain.movement import DELTAS
from .scent import ScentField

# Fixed algorithm constants, not Appendix F game-rule quantities (I6 doesn't
# apply — see PRD 4 Design Question 1's note on heuristic constants, same
# category as movement.DELTAS or CopBrain's tie-break order). The scent
# report's boost is deliberately larger than the tactical hint's: it's
# guaranteed truthful (Revision 1's declared-truthful channel) where the
# hint might be a deliberate lie, so when the two disagree about a region,
# multiplicative reweighting alone (no explicit contradiction-detection
# branch) should still net toward the scent report's region.
_HINT_BOOST = 3.0
_SCENT_REPORT_BOOST = 6.0


@dataclass
class BeliefMap:
    _probabilities: dict[Position, float] = field(default_factory=dict)

    @classmethod
    def uniform(cls, board: Board) -> BeliefMap:
        """The honest "no information yet" prior — not seeded from any
        ground-truth start position (PRD 4 Design Question 2)."""
        cells = [Position(col, row) for col in range(board.size) for row in range(board.size)]
        p = 1.0 / len(cells)
        return cls(_probabilities=dict.fromkeys(cells, p))

    def probability(self, pos: Position) -> float:
        return self._probabilities.get(pos, 0.0)

    def total_probability(self) -> float:
        return sum(self._probabilities.values())

    def most_likely_cell(self) -> Position:
        return max(self._probabilities, key=self._probabilities.get)

    def _normalize(self) -> None:
        total = self.total_probability()
        self._probabilities = {cell: value / total for cell, value in self._probabilities.items()}

    def update_from_scent(self, scent_field: ScentField, cop_pos: Position, board: Board) -> None:
        """Down-weight cells the cop has itself recently searched."""
        for cell, level in scent_field.sample(cop_pos, board).items():
            if cell in self._probabilities:
                self._probabilities[cell] *= 1 - level
        self._normalize()

    def _boost_region(self, focal_point: Position, board: Board, factor: float) -> None:
        cells = {focal_point}
        for direction, delta in DELTAS.items():
            if direction == "STAY":
                continue
            neighbour = focal_point + delta
            if board.in_bounds(neighbour):
                cells.add(neighbour)
        for cell in cells:
            if cell in self._probabilities:
                self._probabilities[cell] *= factor
        self._normalize()

    def update_from_hint(self, focal_point: Position, board: Board) -> None:
        """Up-weight the interpreted (tactical, possibly-lying) hint's focal
        cell and its orthogonal neighbours. `focal_point` comes from
        `reasoning.hint.interpret_hint` — this method doesn't know or care
        whether it's honest or a lie; corroboration against the always-
        truthful scent report (`update_from_scent_report`) is what protects
        against that, not this method itself."""
        self._boost_region(focal_point, board, _HINT_BOOST)

    def update_from_scent_report(self, focal_point: Position, board: Board) -> None:
        """Up-weight the interpreted, always-truthful scent report's focal
        region (Revision 1) — same shape as `update_from_hint`, larger
        boost (`_SCENT_REPORT_BOOST` > `_HINT_BOOST`) reflecting its
        guaranteed honesty. `focal_point` comes from
        `reasoning.hint.interpret_hint` applied to `generate_scent_report`'s
        output, reused unchanged since the vocabulary matches by design."""
        self._boost_region(focal_point, board, _SCENT_REPORT_BOOST)
