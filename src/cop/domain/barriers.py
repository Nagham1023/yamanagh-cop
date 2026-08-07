"""Barrier placement law (book Ch.3): the cop's entire game, per PLAN.md §9.

A cop may place one barrier per turn, only in a turn where it forgoes
movement, and only on its own cell or an orthogonally-adjacent one. Barriers
are permanent — there is no un-placing one. Truthful *declaration* of a
placement (rules 15/16, both **[FATAL]**) is a network-layer concern with a
peer to lie to; it doesn't exist yet in PRD 1's single-process world, so it
isn't enforced here — only the placement rule itself and the quota are.

RULE-15-16-BARRIER-DECLARATION-AT-PRD-6: still true four layers later
(PRD 1 through PRD 5) — barriers placed here are never announced to the
peer over any wire channel; `tools/mcp_server.py`'s tools remain
`receive_hint(text)` and `share_scent_map()` (PRD 4 "Revision 3"), neither
of which carries a barrier declaration. See the guard test in
`tests/unit/test_prd6_missing_wire_channels_guard.py` — delete it, in the
same commit, once PRD 6 makes it pass for real.

Board-bounds checking used to be left to the caller; TODO1.md #1 found that
left a real hole (an off-board target adjacent to a corner cop was silently
accepted, burning quota on a barrier that could never do anything). Bounds
checking now lives here, not in a caller that might forget it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .board import Board, Position


@dataclass
class BarrierSet:
    quota: int
    placed: set[Position] = field(default_factory=set)

    def can_place(self, cop_pos: Position, target: Position, board: Board) -> bool:
        """Bounds, quota, and the one-cell-from-cop rule — all three, together."""
        if not board.in_bounds(target):
            return False
        if len(self.placed) >= self.quota:
            return False
        if target in self.placed:
            return False
        manhattan_distance = abs(target.col - cop_pos.col) + abs(target.row - cop_pos.row)
        return manhattan_distance <= 1

    def place(self, cop_pos: Position, target: Position, board: Board) -> bool:
        """Place a barrier if legal; returns whether it happened. Never applies partially."""
        if not self.can_place(cop_pos, target, board):
            return False
        self.placed.add(target)
        return True

    def blocks(self, pos: Position) -> bool:
        return pos in self.placed
