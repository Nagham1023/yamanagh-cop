"""Bayesian belief heatmap over where the thief is (PRD 4 Design Question
2; genuine Bayes + reliability coefficient, `todoFullFix.md` §E): a real
probability distribution, always renormalized to 1.

`update_from_hint` (`belief_hint_update.py`) is a genuine posterior update —
`P(state|evidence) ∝ P(evidence|state)·P(state)` — not a boost-and-
renormalize heuristic; see that module's own docstring for the reliability-
coefficient reasoning. `_HINT_RELIABILITY`/`_SCENT_MAP_BOOST_SCALE` are
algorithm constants, not Appendix F quantities (I6 doesn't apply, same
category as `movement.DELTAS`) — the book gives the *concept*, not a
number, and this is each team's own algorithm choice, not a negotiated
game rule.

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
from .belief_hint_update import BeliefHintUpdateMixin
from .belief_queries import BeliefQueriesMixin
from .scent import ScentField

_SCENT_MAP_BOOST_SCALE = 20.0


@dataclass
class BeliefMap(BeliefHintUpdateMixin, BeliefQueriesMixin):
    """`most_likely_cell`/`entropy` live in `BeliefQueriesMixin`
    (`belief_queries.py`); `update_from_hint`/`_focal_region` live in
    `BeliefHintUpdateMixin` (`belief_hint_update.py`) — both split out
    once this file hit the 150-line house cap. Everything else that
    *mutates* `_probabilities` stays here."""

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
        """`total == 0.0` is a real, reachable case, not just a theoretical
        one — found immediately after the `update_from_scent` clamp fix
        above shipped: on a small enough board, a cop that has stalled long
        enough can drive *every* tracked cell's multiplier to exactly 0 in
        the same update, and every mutating method funnels through here, so
        this is the one place that needs to defend against it rather than
        each caller separately. Falls back to the same honest "no
        information" uniform prior `uniform()` constructs — a degenerate,
        self-contradicting evidence combination is exactly the case where
        genuinely knowing nothing is the correct belief, not a crash."""
        total = self.total_probability()
        if total <= 0.0:
            free_cells = [cell for cell in self._probabilities if cell not in self._barrier_positions]
            uniform_p = 1.0 / len(free_cells) if free_cells else 0.0
            self._probabilities = {
                cell: (0.0 if cell in self._barrier_positions else uniform_p) for cell in self._probabilities
            }
            return
        self._probabilities = {cell: value / total for cell, value in self._probabilities.items()}

    def update_from_scent(self, scent_field: ScentField, cop_pos: Position, board: Board) -> None:
        """Down-weight cells the cop has itself recently searched.

        `1 - level` is clamped at `0.0`, never left to go negative — found
        live (a real match's `belief.probability()` returned values above
        1.0, an impossible reading caught by the new `belief_target_updated`
        trace event added specifically to watch for this): `ScentField`'s
        own `tau` values are unbounded concentrations, not a `[0, 1]`
        fraction (`scent.py`'s own formula climbs toward a
        `source_strength / decay_rate` steady state — about 9 at the default
        0.9/0.10 — for any cell the cop keeps revisiting, easily exceeding 1
        whenever the cop stalls in place, which is exactly when this method
        matters most). An unclamped `1 - level` then goes negative, and
        multiplying a valid probability by a negative number produces a
        negative one — `_normalize()` only preserves the *sum*, not each
        term's validity, so a handful of corrupted negative cells silently
        pushes *other* cells' normalized share above 1.0 to compensate.
        Clamping keeps this method's own stated intent — down-weight,
        approaching but never crossing zero — true regardless of how large
        `level` gets."""
        for cell, level in scent_field.sample(cop_pos, board).items():
            if cell in self._probabilities:
                self._probabilities[cell] *= max(0.0, 1 - level)
        self._normalize()

    def observe_declaration(self, cell: Position, *, radius: int = 0, trust: float = 0.97) -> None:
        """Fold in a stated position (`capture_claim` -> radius 0, the
        sender claims to stand exactly there; `barrier_placed` -> radius 1,
        the barrier law only allows the placer's own cell or an orthogonal
        neighbor) as direct evidence, separate from the scent channels
        above (PLAN.md Stage 11.4). `trust` is the probability mass placed
        on the declared radius after this call; the remaining `1 - trust`
        stays spread (proportionally, not wiped) over every other
        non-barrier cell, so a single false declaration -- the spec
        permits lying, rule 21/22 -- can never fully blind the belief the
        way `update_from_scent_map`'s own unfakeable signal is allowed to."""
        declared = {
            pos
            for pos in self._probabilities
            if pos not in self._barrier_positions
            and abs(pos.col - cell.col) + abs(pos.row - cell.row) <= radius
        }
        total_declared = sum(self._probabilities[pos] for pos in declared)
        remaining = self.total_probability() - total_declared
        if total_declared <= 0.0 or remaining <= 0.0:
            return  # degenerate distribution -- nothing sane to reweight
        boost = trust / total_declared
        fade = (1.0 - trust) / remaining
        for pos in self._probabilities:
            if pos in self._barrier_positions:
                continue
            self._probabilities[pos] *= boost if pos in declared else fade
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
