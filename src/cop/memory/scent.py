"""The agent's own pheromone trail (Table 16, Figure 4) — PRD 4 Revision 1,
Design Question 1.

Ch. 4.3/Figure 4 of the book define emission as a fixed radial 5x5 kernel
around the emitting cell, decayed and re-deposited once per full turn via
`tau(t+1) = max(0, (1-rho)*tau(t) + delta_tau)` — not the single-cell point
deposit the original PRD 4 build used. `ScentField` still serves its
original purpose (down-weighting the agent's own recently-searched cells,
`memory/belief.py`'s `update_from_scent`) and now also serves as the honest
source for the outgoing scent report (`reasoning/hint.py`'s
`generate_scent_report`) that lets the receiver corroborate an incoming
hint against real, always-truthful data — the mechanic PRD-4-language-and-
scent.md's "Revision 1" section works out how to transmit legally under
rule 26/27.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.board import Board, Position
from ..shared.config import GameConfig

# Figure 4's reference case: the 25 kernel values below are given for
# source_strength = 0.9. Stored as a fixed *relative* shape and scaled by
# source_strength / _REFERENCE_STRENGTH at emission time (I6 — genuinely
# config-driven, not a hardcoded illustration), numerically identical to
# Figure 4 under the actual configured value.
_REFERENCE_STRENGTH = 0.9

# Row-major, top-to-bottom = row offset -2..+2, left-to-right = column
# offset -2..+2 — laid out exactly as Figure 4 prints it (page 44), so the
# table is a direct transcription, not a hand-assembled dict prone to a
# transposed or off-by-one entry.
_KERNEL_GRID = [
    [0.04, 0.14, 0.20, 0.14, 0.04],
    [0.14, 0.42, 0.62, 0.42, 0.14],
    [0.20, 0.62, 0.90, 0.62, 0.20],
    [0.14, 0.42, 0.62, 0.42, 0.14],
    [0.04, 0.14, 0.20, 0.14, 0.04],
]
_KERNEL: dict[tuple[int, int], float] = {
    (d_col, d_row): value
    for d_row, row in enumerate(_KERNEL_GRID, start=-2)
    for d_col, value in enumerate(row, start=-2)
}


@dataclass
class ScentField:
    source_strength: float
    decay_rate: float
    window_size: int
    _levels: dict[Position, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # The hardcoded 5x5 _KERNEL has no meaning at another window size.
        # Table 16 marks scent_field_size FIXED, so this is a real
        # invariant to fail loudly on, not speculative future-proofing.
        if self.window_size != 5:
            raise ValueError(
                f"ScentField's radial kernel is fixed at 5x5 (Figure 4); "
                f"got window_size={self.window_size}"
            )

    @classmethod
    def from_config(cls, config: GameConfig) -> ScentField:
        """All three constants sourced from `GameConfig`, never a literal (I6)."""
        return cls(
            source_strength=config.scent_source_strength,
            decay_rate=config.scent_decay_rate,
            window_size=config.scent_field_size,
        )

    def advance(self, pos: Position, board: Board) -> None:
        """One full-turn update: `tau(t+1) = max(0, (1-rho)*tau(t) + delta_tau)`,
        applied to every tracked cell in a single atomic step. Decays all
        existing levels first, then adds this turn's radial kernel deposit
        around `pos` (clipped to board bounds) on top of the decayed values
        — the fresh deposit is never itself decayed in the same step it
        lands, matching the book's formula exactly (Design Question 1)."""
        factor = 1 - self.decay_rate
        decayed = {p: level * factor for p, level in self._levels.items()}
        scale = self.source_strength / _REFERENCE_STRENGTH
        for (d_col, d_row), value in _KERNEL.items():
            candidate = Position(pos.col + d_col, pos.row + d_row)
            if board.in_bounds(candidate):
                decayed[candidate] = decayed.get(candidate, 0.0) + value * scale
        self._levels = {p: max(0.0, level) for p, level in decayed.items()}

    def sample(self, center: Position, board: Board) -> dict[Position, float]:
        """The `window_size` x `window_size` window around `center`, clipped to
        board bounds. Cells never emitted at read as 0.0, not missing."""
        half = self.window_size // 2
        result: dict[Position, float] = {}
        for d_col in range(-half, half + 1):
            for d_row in range(-half, half + 1):
                candidate = Position(center.col + d_col, center.row + d_row)
                if board.in_bounds(candidate):
                    result[candidate] = self._levels.get(candidate, 0.0)
        return result
