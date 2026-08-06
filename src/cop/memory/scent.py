"""The cop's own pheromone trail (Table 16) — PRD 4 Design Question 1.

Not a signal received from or about the opponent: nothing on the wire could
carry that without becoming a second numeric-position channel (rule 27, a
different violation). `ScentField` is the cop's own decaying record of
where *it* has recently searched, used to down-weight those cells in
`memory/belief.py`'s update — reducing redundant re-searching, not sensing
the thief.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.board import Board, Position
from ..shared.config import GameConfig


@dataclass
class ScentField:
    source_strength: float
    decay_rate: float
    window_size: int
    _levels: dict[Position, float] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: GameConfig) -> ScentField:
        """All three constants sourced from `GameConfig`, never a literal (I6)."""
        return cls(
            source_strength=config.scent_source_strength,
            decay_rate=config.scent_decay_rate,
            window_size=config.scent_field_size,
        )

    def emit(self, pos: Position) -> None:
        """Deposit a fresh trace at `pos` — called with the cop's own current position."""
        self._levels[pos] = self.source_strength

    def decay(self) -> None:
        """Reduce every cell's level by `decay_rate`, once per turn."""
        factor = 1 - self.decay_rate
        self._levels = {pos: level * factor for pos, level in self._levels.items()}

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
