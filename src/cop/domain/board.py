"""Board geometry: the discrete grid every other domain module measures against.

`Board` knows nothing about barriers, agents, or turns — only which cells
exist. Keeping geometry separate from occupancy is what lets movement,
barriers, and capture be tested independently of each other.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    """A single cell as (col, row), matching the book's origin convention:
    top-left corner, index 0 (Table 13, board_size/origin/index_base)."""

    col: int
    row: int

    def __add__(self, other: Position) -> Position:
        return Position(self.col + other.col, self.row + other.row)


@dataclass(frozen=True)
class Board:
    size: int

    def in_bounds(self, pos: Position) -> bool:
        return 0 <= pos.col < self.size and 0 <= pos.row < self.size
