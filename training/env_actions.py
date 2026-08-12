"""Cop-action resolution for `SelfPlayEnv` (PRD 14 sub-layer B) — split out
of `env.py` once its own `step()` grew past the 150-line house cap
alongside the new barrier action space.
"""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.domain.capture import is_barrier_capture
from cop.domain.movement import DELTAS, apply_move
from cop.reasoning.cop_brain import CopBrain

_ORTHOGONAL_DIRECTIONS = ("N", "E", "S", "W")


def _open_move_directions(cop_pos: Position, board: Board, barriers: BarrierSet) -> list[str]:
    """Directions that are actually walkable right now: in-bounds *and* not
    barrier-blocked. `apply_move` alone only checks bounds — every real
    movement-legality caller (`CopBrain._pick_move`) additionally checks
    `barriers.blocks(destination)`; this was missing here (a real bug: the
    cop's own placed barriers were being offered, and stepped onto, as
    ordinary legal moves) until this fix."""
    open_directions = []
    for direction in _ORTHOGONAL_DIRECTIONS:
        destination = apply_move(cop_pos, direction, board)
        if destination is not None and not barriers.blocks(destination):
            open_directions.append(direction)
    return open_directions


def legal_cop_actions(cop_pos: Position, board: Board, barriers: BarrierSet) -> list[str]:
    """Movement actions plus `BARRIER_<dir>` for each of the cop's
    orthogonal neighbours `BarrierSet.can_place` actually allows right now
    (quota, adjacency, bounds — never reinvented here). An over-quota or
    otherwise illegal placement simply never appears — the same
    enforcement shape movement already uses, not present-then-rejected.

    A barrier candidate that would seal the cop's own *last* open move is
    also excluded — found empirically (a trained policy walled itself in
    and then spent the rest of every episode STAY-looping to a SURVIVAL
    timeout instead of ever reaching the thief again). `CopBrain`'s own
    heuristic avoids this by construction (`_barrier_candidates` excludes
    its own preferred next step); nothing in the learned Q-table process
    shared that guarantee before this check existed."""
    open_directions = _open_move_directions(cop_pos, board, barriers)
    legal = ["STAY", *open_directions]
    for direction in _ORTHOGONAL_DIRECTIONS:
        candidate = cop_pos + DELTAS[direction]
        if not barriers.can_place(cop_pos, candidate, board):
            continue
        if direction in open_directions and len(open_directions) == 1:
            continue  # would leave the cop with zero moves, only STAY forever
        legal.append(f"BARRIER_{direction}")
    return legal


def apply_cop_action(
    action: str, cop_pos: Position, thief_pos: Position, board: Board, barriers: BarrierSet
) -> tuple[Position, bool]:
    """Resolves one cop action — a move, or a barrier placement that
    forgoes movement — against the board and barrier set (`barriers` is
    mutated in place on a successful placement, matching `BarrierSet.place`'s
    own contract). Returns `(new_cop_pos, barrier_capture)`:
    `barrier_capture` is rule 46's unconditional check against the *true*
    `thief_pos`, never gated on belief — mirrors `run_local_subgame`'s own
    check exactly.

    Re-checks legality via `BarrierSet.can_place` rather than trusting
    `SelfPlayEnv.legal_actions()` alone — an illegal proposal (reachable
    only if a caller bypasses that filter) is a safe no-op, the same
    defensive posture a barrier-blocked move gets below.

    A movement destination is also re-checked against `barriers.blocks`,
    not just `apply_move`'s board-bounds check — `apply_move` alone has no
    notion of barriers at all, so before this check a cop could "move" onto
    (or through) a cell it had itself barriered. Matches
    `CopBrain._pick_move`'s own combined check exactly."""
    if action.startswith("BARRIER_"):
        direction = action.removeprefix("BARRIER_")
        target = cop_pos + DELTAS[direction]
        if barriers.can_place(cop_pos, target, board):
            barriers.place(cop_pos, target, board)
            return cop_pos, is_barrier_capture(target, thief_pos)
        return cop_pos, False
    destination = apply_move(cop_pos, action, board)
    if destination is None or barriers.blocks(destination):
        return cop_pos, False
    return destination, False


def barrier_restricts_believed_target(
    action: str, cop_pos_before_action: Position, believed_target_pos: Position, barriers: BarrierSet
) -> bool:
    """PRD 14 post-gate follow-up: True iff `action` was a barrier placement
    that (a) actually succeeded — confirmed via `barriers.placed`, not
    assumed from `action`'s shape alone, since an illegal proposal is a
    safe no-op above — and (b) restricts the *believed* target's escape
    routes, reusing `CopBrain._restricts_target` directly (the same
    already-tested definition `CopBrain`'s own barrier heuristic uses,
    never re-derived). See `reward.py`'s own docstring for why this feeds a
    reward bonus and its honesty caveat; see `env.py::step`'s own docstring
    for why `believed_target_pos` must be read *before* this action runs."""
    if not action.startswith("BARRIER_"):
        return False
    candidate = cop_pos_before_action + DELTAS[action.removeprefix("BARRIER_")]
    if candidate not in barriers.placed:
        return False
    return CopBrain._restricts_target(candidate, believed_target_pos)
