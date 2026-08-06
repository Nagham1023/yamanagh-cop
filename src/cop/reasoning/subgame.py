"""Local turn loop — the PRD 3 milestone (Design Question 3).

Pure Python, no `Orchestrator`, no network, no subprocess: drives the cop
brain and a thief-mover function directly against `domain/` primitives, so
a failure here is isolated to a `reasoning/`+`domain/` bug, never a
networking one. `Orchestrator.take_turn()` proves the brain is wired to the
real peer; this proves the algorithm itself is correct.
"""

from __future__ import annotations

from collections.abc import Callable

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..domain.capture import is_barrier_capture, is_coordinate_capture, thief_has_no_legal_move
from ..domain.end_conditions import determine_outcome
from ..domain.movement import apply_move
from ..domain.scoring import Outcome
from ..shared.config import GameConfig
from .brain_base import Action, BrainBase, PlaceBarrier
from .state import GameState

ThiefMover = Callable[[Position, Board, BarrierSet], str]
OnTurn = Callable[[int, Action, Position, Position], None]


def run_local_subgame(
    cop_brain: BrainBase,
    thief_mover: ThiefMover,
    board: Board,
    config: GameConfig,
    on_turn: OnTurn | None = None,
) -> Outcome:
    """Alternate cop/thief turns from `config`'s start positions until
    `domain.end_conditions.determine_outcome` returns a real `Outcome`.

    One `while` iteration is one round (a cop decision counts as one step
    toward `step_ceiling` — see `GameState.apply`'s docstring). All three
    capture shapes are checked together after the cop's action: coordinate
    capture, a barrier landing on the thief's cell (rule 46), and the thief
    having zero legal moves left (rule 47) — `determine_outcome` then
    applies its own capture-before-ceiling precedence.

    `on_turn`, if given, is called once per round with
    `(round_number, action, cop_pos, thief_pos)` right after the cop's
    action is applied — the same `on_receive`-style optional observability
    hook PRD 2's `build_server` uses, so the demo script can narrate
    progress without a second copy of this loop.
    """
    cop_state = GameState(
        own_pos=Position(*config.cop_start),
        target_pos=Position(*config.thief_start),
        barriers=BarrierSet(quota=config.barrier_quota),
    )
    thief_pos = Position(*config.thief_start)
    round_number = 0

    while True:
        round_number += 1
        cop_state.target_pos = thief_pos
        action = cop_brain._decide_move(cop_state.own_pos, thief_pos, board, cop_state.barriers)
        barrier_capture = isinstance(action, PlaceBarrier) and is_barrier_capture(
            action.target, thief_pos
        )
        cop_state.apply(action, board)
        if on_turn is not None:
            on_turn(round_number, action, cop_state.own_pos, thief_pos)

        captured = (
            barrier_capture
            or is_coordinate_capture(cop_state.own_pos, thief_pos)
            or thief_has_no_legal_move(thief_pos, board, cop_state.barriers)
        )
        outcome = determine_outcome(
            captured=captured,
            steps_taken=cop_state.steps_taken,
            step_ceiling=config.step_ceiling,
            survival_threshold=config.survival_threshold,
        )
        if outcome is not None:
            return outcome

        thief_direction = thief_mover(thief_pos, board, cop_state.barriers)
        # `thief_mover` is a caller-supplied callable, not an internal
        # invariant — fall back to staying in place on an illegal proposal
        # rather than crashing the loop on untrusted input.
        thief_pos = apply_move(thief_pos, thief_direction, board) or thief_pos
