"""Test/demo scaffolding only — NOT a ThiefBrain (PRD 3 Design Question 5).

`thief_class` is the teammate's own separate repo's concern (Table 22:
"private per peer, not negotiated"). This is a plain function, not a
`BrainBase` subclass, used only to give `CopBrain` something to chase in
local tests and the PRD 3 demo script. Never imported by anything under
`src/cop/` — the actual rule-1 boundary to watch is that import direction,
not this fixture's mere existence.
"""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.domain.movement import DELTAS, apply_move

_TIE_BREAK_ORDER = ("N", "E", "S", "W")


def greedy_thief_move(own_pos: Position, board: Board, barriers: BarrierSet) -> str:
    """Prefer the neighbour with the most open orthogonal neighbours of its
    own (an escape-route count) — `PLAN.md`'s "also verify" line for PRD 3.
    `STAY` only when every orthogonal move is illegal, off-board, or
    barrier-blocked, same convention as `CopBrain._pick_move`."""
    candidates: list[tuple[int, str]] = []
    for direction in _TIE_BREAK_ORDER:
        destination = apply_move(own_pos, direction, board)
        if destination is None or barriers.blocks(destination):
            continue
        escape_routes = _count_open_neighbours(destination, board, barriers)
        candidates.append((escape_routes, direction))

    if not candidates:
        return "STAY"
    return max(candidates, key=lambda pair: pair[0])[1]


def _count_open_neighbours(pos: Position, board: Board, barriers: BarrierSet) -> int:
    """Reuses `board.in_bounds` + `barriers.blocks` — no reimplemented scan."""
    count = 0
    for direction, delta in DELTAS.items():
        if direction == "STAY":
            continue
        neighbour = pos + delta
        if board.in_bounds(neighbour) and not barriers.blocks(neighbour):
            count += 1
    return count
