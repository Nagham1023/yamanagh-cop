"""Per-turn mutable state a brain reasons over (PRD 3 Design Question 1).

`target_pos` is ground truth for this layer — PRD 4 replaces *where this
value comes from* (the belief map's most likely cell), not this class's
shape. Not `memory/`'s territory: that module is specifically the
*uncertain* belief/scent apparatus PRD 4 introduces.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..domain.movement import apply_move
from .brain_base import Action, Move, PlaceBarrier


@dataclass
class GameState:
    """Mutable, unlike `Board`/`Position`: position and step count change every turn."""

    own_pos: Position
    target_pos: Position
    barriers: BarrierSet
    steps_taken: int = 0

    def apply(self, action: Action, board: Board) -> None:
        """Apply one decided `Action` in place.

        `steps_taken` counts turns, not cells moved — a barrier-placement
        turn (which forgoes movement, per the Ch.3 mechanic) still consumes
        a step toward `step_ceiling`, same as a move does; both are one
        turn each in a turn-based pursuit game.

        Raises `ValueError` on an illegal action rather than silently
        no-op'ing into a different one — an illegal `Action` reaching here
        means the brain that produced it has a bug, and that should fail
        loudly, not be absorbed.
        """
        match action:
            case Move(direction=direction):
                destination = apply_move(self.own_pos, direction, board)
                if destination is None or self.barriers.blocks(destination):
                    raise ValueError(f"illegal move: {direction!r} from {self.own_pos!r}")
                self.own_pos = destination
            case PlaceBarrier(target=target):
                if not self.barriers.place(self.own_pos, target, board):
                    raise ValueError(f"illegal barrier placement at {target!r}")
        self.steps_taken += 1
