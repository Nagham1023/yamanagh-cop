"""CopBrain: greedy Manhattan-distance pursuit (PLAN.md §5's suggested heuristic).

`_pick_move`'s legality check reuses `domain.movement.apply_move` (bounds)
and `barriers.blocks` (occupancy) rather than reimplementing either — the
brain proposes moves, `domain/` still validates them (PRD 3's "Builds on").
`_decide_move`'s barrier policy adds the Table 22 barrier choice.
"""

from __future__ import annotations

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..domain.movement import DELTAS, apply_move
from .brain_base import Action, BrainBase, Move, PlaceBarrier

# Fixed direction priority for tie-breaking equal-distance candidates. Not a
# game-rule quantity (I6 doesn't apply) — an algorithm implementation
# choice, the same category `movement.DELTAS` already occupies.
_TIE_BREAK_ORDER = ("N", "E", "S", "W")


class CopBrain(BrainBase):
    """Greedy Manhattan-distance descent toward the target, perfect information."""

    def _pick_move(
        self, own_pos: Position, target_pos: Position, board: Board, barriers: BarrierSet
    ) -> str:
        """Among legal orthogonal moves, pick the one minimizing Manhattan distance
        to `target_pos`. `STAY` only when every orthogonal move is illegal,
        off-board, or barrier-blocked."""
        candidates: list[tuple[int, str]] = []
        for direction in _TIE_BREAK_ORDER:
            destination = apply_move(own_pos, direction, board)
            if destination is None or barriers.blocks(destination):
                continue
            distance = abs(destination.col - target_pos.col) + abs(destination.row - target_pos.row)
            candidates.append((distance, direction))

        if not candidates:
            return "STAY"
        return min(candidates, key=lambda pair: pair[0])[1]

    def _decide_move(
        self, own_pos: Position, target_pos: Position, board: Board, barriers: BarrierSet
    ) -> Action:
        """Forgo movement and place a barrier when a candidate is placeable
        (own-cell-or-adjacent, quota, bounds — `BarrierSet.can_place`),
        restricts one of the target's own escape routes, and is not the
        cop's own preferred next step (found via reproduction: barricading
        your own single best path toward the target is self-defeating — it
        can strand the greedy `_pick_move` heuristic in a permanent
        oscillation between its two next-best options, since it has no
        lookahead to route around its own obstacle).

        That exclusion also structurally guarantees the cop never walls
        itself off, with no separate self-trap check needed: candidates are
        drawn from exactly the same 4 orthogonal neighbours `_pick_move`
        itself considers (see `_barrier_candidates`), so a candidate could
        only ever reduce the cop's open neighbours to zero if it were the
        *only* one left open — and in that case it's necessarily also the
        (only) preferred destination, already excluded above. An earlier
        version carried an explicit `_would_self_trap` check reusing
        `capture.thief_has_no_legal_move`; coverage analysis proved its
        `True` branch was unreachable for exactly this reason, so it was
        removed rather than kept as untested dead code.

        No numeric threshold (I6 doesn't apply to this internal heuristic
        shape either way) — "restricts" means the candidate is literally
        one of the target's open neighbours, not a tunable distance. Falls
        back to `_pick_move` otherwise."""
        preferred_direction = self._pick_move(own_pos, target_pos, board, barriers)
        preferred_destination = apply_move(own_pos, preferred_direction, board)
        for candidate in self._barrier_candidates(own_pos, board, barriers):
            if candidate == preferred_destination:
                continue
            if not self._restricts_target(candidate, target_pos):
                continue
            return PlaceBarrier(target=candidate)
        return Move(direction=preferred_direction)

    @staticmethod
    def _barrier_candidates(own_pos: Position, board: Board, barriers: BarrierSet) -> list[Position]:
        """The cop's 4 orthogonal neighbours only — not its own cell, which
        doesn't restrict the target's escape routes at all."""
        candidates = []
        for direction, delta in DELTAS.items():
            if direction == "STAY":
                continue
            candidate = own_pos + delta
            if barriers.can_place(own_pos, candidate, board):
                candidates.append(candidate)
        return candidates

    @staticmethod
    def _restricts_target(candidate: Position, target_pos: Position) -> bool:
        """True only if `candidate` is one of the target's orthogonal neighbours."""
        return abs(candidate.col - target_pos.col) + abs(candidate.row - target_pos.row) == 1
