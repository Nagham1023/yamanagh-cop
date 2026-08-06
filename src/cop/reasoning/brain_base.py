"""BrainBase contract (rule 25, I7): the first move-deciding code in this repo.

Not the book reference repo's own `BrainBase`/`ThiefBrain` hierarchy
(github.com/rmisegal/Game-P2P-Cop-Chase) — ours is scoped to exactly what
this repo needs (PRD 3 Design Question 5: this repo builds a real cop brain
only, never a thief brain). A mismatch with the reference repo's class
names is not a bug.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position


@dataclass(frozen=True)
class Move:
    """Take one step — `direction` is one of `domain.movement.DELTAS`' keys."""

    direction: str


@dataclass(frozen=True)
class PlaceBarrier:
    """Forgo movement this turn and place a barrier at `target` instead."""

    target: Position


Action = Move | PlaceBarrier


class BrainBase(ABC):
    """The observe -> decide -> act contract every brain in this repo implements.

    Split into two methods on purpose: `_pick_move` is the movement-only
    half every brain needs, `_decide_move` is the full per-turn decision —
    the cop overrides `_decide_move` to add the barrier choice (Table 22),
    the default here just wraps `_pick_move`'s result.
    """

    @abstractmethod
    def _pick_move(
        self, own_pos: Position, target_pos: Position, board: Board, barriers: BarrierSet
    ) -> str:
        """Return one of `domain.movement.DELTAS`' keys — movement only, no barrier choice."""

    def _decide_move(
        self, own_pos: Position, target_pos: Position, board: Board, barriers: BarrierSet
    ) -> Action:
        """Default per-turn decision: just move. Overridden where more choices exist."""
        return Move(self._pick_move(own_pos, target_pos, board, barriers))
