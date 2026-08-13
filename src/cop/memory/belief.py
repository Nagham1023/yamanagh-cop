"""Bayesian belief heatmap over where the thief is (PRD 4 Design Question
2; genuine Bayes + reliability coefficient, `todoFullFix.md` §E): a real
probability distribution, always renormalized to 1.

`update_from_hint` is a genuine posterior update — `P(state|evidence) ∝
P(evidence|state)·P(state)` — not a boost-and-renormalize heuristic. The
hint's *focal region* (`_focal_region`) gets likelihood `_HINT_RELIABILITY`;
every other tracked cell gets `(1-_HINT_RELIABILITY)/N`. Ch. 6.4's own
"מקדם אמינות" (reliability coefficient) applies specifically to text
evidence, since text may lie (Table 21's `Intent`) — elsewhere cells are
now actively down-weighted, not merely left unchanged, the real second half
of a Bayesian update a flat boost never did. `_HINT_RELIABILITY`/
`_SCENT_MAP_BOOST_SCALE` are algorithm constants, not Appendix F quantities
(I6 doesn't apply, same category as `movement.DELTAS`) — the book gives the
*concept*, not a number, and this is each team's own algorithm choice, not
a negotiated game rule.

`update_from_scent_map` (PRD 4 "Revision 3", §C6, finalized here) scales
each cell's likelihood with the peer's own real tau magnitude — genuine
per-cell data, not a single re-quantized focal point. `update_from_scent`
down-weights cells the cop has itself recently searched.

Barrier cells carry exactly zero belief (Figure 8's own caption) — real
domain knowledge: the thief cannot occupy a blocked cell. `_barrier_positions`
is remembered explicitly so `most_likely_cell()` can filter them
defensively even if a caller forgets to re-zero after a new placement —
"never trust a single enforcement layer" (rule 27's word-limit backstop is
the precedent). Every *non-barrier* cell still never hits exactly 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..domain.movement import DELTAS
from .belief_queries import BeliefQueriesMixin
from .scent import ScentField

_HINT_RELIABILITY = 0.6
_SCENT_MAP_BOOST_SCALE = 20.0


@dataclass
class BeliefMap(BeliefQueriesMixin):
    """`most_likely_cell`/`entropy` live in `BeliefQueriesMixin`
    (`belief_queries.py`) — split out once this file hit the 150-line
    house cap; everything that *mutates* `_probabilities` stays here."""

    _probabilities: dict[Position, float] = field(default_factory=dict)
    _barrier_positions: frozenset[Position] = field(default_factory=frozenset)

    @classmethod
    def uniform(cls, board: Board, barriers: BarrierSet | None = None) -> BeliefMap:
        """The honest "no information yet" prior — not seeded from any
        ground-truth start position (PRD 4 Design Question 2). `barriers`
        is optional (typically empty at game start) — cells it already
        covers seed at exactly 0, everything else splits the mass evenly."""
        barrier_positions = frozenset(barriers.placed) if barriers is not None else frozenset()
        cells = [Position(col, row) for col in range(board.size) for row in range(board.size)]
        free_cells = [c for c in cells if c not in barrier_positions]
        p = 1.0 / len(free_cells) if free_cells else 0.0
        probabilities = {c: (0.0 if c in barrier_positions else p) for c in cells}
        return cls(_probabilities=probabilities, _barrier_positions=barrier_positions)

    def probability(self, pos: Position) -> float:
        return self._probabilities.get(pos, 0.0)

    def total_probability(self) -> float:
        return sum(self._probabilities.values())

    def zero_out_barriers(self, barriers: BarrierSet) -> None:
        """Re-sync belief with the current, possibly-grown barrier set —
        called again whenever a new barrier is placed, not just at
        construction. Idempotent: re-zeroing an already-zero cell is safe."""
        self._barrier_positions = frozenset(barriers.placed)
        for pos in self._barrier_positions:
            if pos in self._probabilities:
                self._probabilities[pos] = 0.0
        self._normalize()

    def _normalize(self) -> None:
        total = self.total_probability()
        self._probabilities = {cell: value / total for cell, value in self._probabilities.items()}

    def update_from_scent(self, scent_field: ScentField, cop_pos: Position, board: Board) -> None:
        """Down-weight cells the cop has itself recently searched."""
        for cell, level in scent_field.sample(cop_pos, board).items():
            if cell in self._probabilities:
                self._probabilities[cell] *= 1 - level
        self._normalize()

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

    def update_from_scent_map(self, scent_data: dict[Position, float], board: Board) -> None:
        """Up-weight every cell proportionally to the peer's own real scent
        magnitude there (PRD 4 "Revision 3", `todoFullFix.md` §C6/§E) —
        replaces `update_from_scent_report`'s single re-quantized focal
        point. `scent_data` is the peer's `ScentField.full_field()`, pulled
        via `Orchestrator.request_scent_map_from_peer` — genuine per-cell
        tau values, un-lie-able by construction (Intent never applies to
        this channel). A strong reading boosts its cell more than a faint
        one; a cell absent from `scent_data` (never touched by the peer)
        gets no direct boost — its *share* of the total still shrinks as
        other cells grow, the same "absence means zero" convention
        `ScentField.sample`/`full_field` already use.
        """
        for cell, value in scent_data.items():
            if cell in self._probabilities and value > 0:
                self._probabilities[cell] *= 1 + _SCENT_MAP_BOOST_SCALE * value
        self._normalize()
