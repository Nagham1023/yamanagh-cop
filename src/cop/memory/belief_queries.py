"""Read-only derived queries over `BeliefMap`'s own `_probabilities` — split
out once `belief.py` grew past the 150-line house cap adding these.
`BeliefMap` inherits this mixin (same "split one logical class across
files" precedent `orchestrator_turn.py::BrainTurnMixin` already set) rather
than these living as free functions reaching into a private attribute from
outside — preserves encapsulation.
"""

from __future__ import annotations

import math

from ..domain.board import Position


class BeliefQueriesMixin:
    """Expects `self._probabilities: dict[Position, float]` and
    `self._barrier_positions: frozenset[Position]` — `BeliefMap`'s own
    fields, per the dataclass this mixin is combined with."""

    def most_likely_cell(self) -> Position:
        candidates = {c: p for c, p in self._probabilities.items() if c not in self._barrier_positions}
        if not candidates:
            candidates = self._probabilities  # defensive: should never happen (barriers < board cells)
        return max(candidates, key=candidates.get)

    def entropy(self) -> float:
        """Shannon entropy `H(b) = -sum(p * ln(p))` over nonzero-probability
        cells only — `0 * ln(0) = 0` by the standard information-theory
        convention, so barrier/untouched cells (already exactly 0) never
        call `math.log(0)`. A point-mass distribution (perfect information)
        has entropy exactly `0.0` — not a stand-in default, the
        mathematically exact value `rl_state_encoding.encode_state`'s own
        `belief_entropy=0.0` default relies on. Natural log throughout this
        repo's own entropy bucketing (`belief_entropy_bucket.py`) — its own
        thresholds are chosen relative to `ln(board_size**2)`."""
        return -sum(p * math.log(p) for p in self._probabilities.values() if p > 0.0)

    def expected_manhattan_distance(self, cop_pos: Position) -> float:
        """`sum(p * manhattan(cell, cop_pos))` over nonzero-probability
        cells — the expected distance under the FULL belief distribution,
        not just distance to the single argmax cell. Reduces to exactly
        the ground-truth Manhattan distance when belief is a point mass at
        the true position (`training/reward.py`'s own docstring covers why
        this is *not* automatically as provably safe a shaping signal as
        that ground-truth term, despite the algebraic resemblance)."""
        return sum(
            p * (abs(cell.col - cop_pos.col) + abs(cell.row - cop_pos.row))
            for cell, p in self._probabilities.items()
            if p > 0.0
        )

    def second_mode(
        self, primary: Position, *, min_separation: int = 3, min_relative_mass: float = 0.3
    ) -> Position | None:
        """The highest-probability cell at least `min_separation` Manhattan
        distance from `primary` (the caller's own `most_likely_cell()`)
        whose own probability is at least `min_relative_mass` of `primary`'s
        — the working definition of "a second real mode," not a noisy
        shoulder of the same peak (two adjacent high cells from one soft
        peak must NOT count as bimodal). `None` in the common, genuinely-
        unimodal case. `min_separation`/`min_relative_mass` are algorithm
        constants (I6 doesn't apply — same category as `_CLAMP_RADIUS`/
        `ENTROPY_THRESHOLDS`), meant to be revisited against real coverage
        measurement (`scripts/measure_bimodal_coverage.py`), not guessed
        once and left untouched."""
        primary_prob = self._probabilities.get(primary, 0.0)
        if primary_prob <= 0.0:
            return None
        floor = primary_prob * min_relative_mass
        candidates = {
            cell: p
            for cell, p in self._probabilities.items()
            if cell not in self._barrier_positions
            and p >= floor
            and (abs(cell.col - primary.col) + abs(cell.row - primary.row)) >= min_separation
        }
        if not candidates:
            return None
        return max(candidates, key=candidates.get)
