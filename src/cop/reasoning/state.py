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


def ground_truth_target_position(true_thief_position: Position) -> Position:
    """The single seam PRD 4 replaces (Design Question 4).

    Every place in this repo that turns "the true thief position" into a
    `target_pos` value — `Orchestrator.__init__` and `subgame.run_local_subgame`,
    both of which read a true position from a different source (config vs. a
    live simulation variable) — routes through this one function. Its body
    is the identity today; PRD 4 swaps it for a belief-map lookup without
    touching either caller. Kept identity-trivial on purpose: the point is
    the seam, not the logic behind it, which doesn't exist until PRD 4.
    """
    return true_thief_position


@dataclass(kw_only=True)
class GameState:
    """Mutable, unlike `Board`/`Position`: position and step count change every turn.

    Keyword-only on purpose: `tests/unit/test_prd4_seam.py`'s AST check for
    `ground_truth_target_position` usage only inspects keyword arguments and
    attribute assignments — a positional `GameState(own, thief, barriers)`
    call would silently bypass it. `kw_only=True` makes that construction a
    `TypeError`, closing the gap structurally instead of just detecting it
    (found during `rule-auditor`'s review of the seam test itself).
    """

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
