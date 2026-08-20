"""escape_area: BFS-bounded reachable-area scorer (PLAN.md Stage 11.4).

A cop maximizing raw Manhattan distance-closing is provably beaten by a
distance-maximizing evader on an open board: once distance parity is
reached, no gradient toward capture exists for a pure pursuit policy (see
PLAN.md Stage 11.1 -- confirmed both by this project's own real matches and
by independent research). The real lever is architecture, not speed: how
much of the board the opponent can still reach. `escape_area` counts
reachable cells via a depth-bounded BFS, so a candidate move or barrier
placement can be scored by how much it *shrinks* the opponent's own
reachable world, not by distance to a single believed cell.
"""

from __future__ import annotations

from collections import deque

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..domain.movement import DELTAS

DEFAULT_MAX_STEPS = 4


def escape_area(
    start: Position, board: Board, barriers: BarrierSet, max_steps: int = DEFAULT_MAX_STEPS
) -> int:
    """Count of distinct cells reachable from `start` within `max_steps`
    orthogonal moves, treating barrier cells as impassable walls.
    Depth-bounded rather than a full-board flood fill: one wall's effect on
    *global* connectivity is nearly invisible on an open board (7x7: one
    wall only ever changes 49 reachable cells to 48), so a 1-ply search
    scored on global area never finds the first funnel wall worth playing.
    The signal only shows up locally, near the opponent's own position --
    which is exactly the region this bound keeps legible."""
    visited = {start}
    frontier = deque([(start, 0)])
    while frontier:
        pos, depth = frontier.popleft()
        if depth == max_steps:
            continue
        for delta in DELTAS.values():
            if delta == Position(0, 0):
                continue  # STAY -- not a move to a new cell
            neighbor = pos + delta
            if neighbor in visited:
                continue
            if not board.in_bounds(neighbor) or barriers.blocks(neighbor):
                continue
            visited.add(neighbor)
            frontier.append((neighbor, depth + 1))
    return len(visited)
