"""`_legal_directions` split out of `rl_cop_brain.py` once that file grew
past the 150-line house cap adding the `second_mode_provider` seam — a
single, self-contained helper with no other coupling to the rest of that
file.
"""

from __future__ import annotations

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..domain.capture import thief_has_no_legal_move
from ..domain.movement import DELTAS, apply_move


def legal_directions(own_pos: Position, board: Board, barriers: BarrierSet) -> set[str]:
    """Every direction whose destination is on-board and unblocked, plus
    `STAY` (always legal) — the same check `CopBrain._pick_move` already
    performs per-candidate, computed once here as a set for a ranked-list
    intersection."""
    legal = {"STAY"}
    for direction in DELTAS:
        if direction == "STAY":
            continue
        destination = apply_move(own_pos, direction, board)
        if destination is not None and not barriers.blocks(destination):
            legal.add(direction)
    return legal


_OPPOSITE_DIRECTION = {"N": "S", "S": "N", "E": "W", "W": "E"}


def opposite_direction(direction: str | None) -> str | None:
    """`None` for `None`/`"STAY"`/an unrecognized token — only N/E/S/W have
    a real opposite. Exposed separately from `pick_avoiding_backtrack` for
    callers (like `RLCopBrain._decide_move`) that interleave move and
    barrier candidates and can't use that function's flat scan directly."""
    return _OPPOSITE_DIRECTION.get(direction) if direction else None


def pick_avoiding_backtrack(ranked: list[str], legal: set[str], last_direction: str | None) -> str | None:
    """Found by actually running a promoted checkpoint against a real
    opponent (round 2 post-gate): a tabular table can have a sparsely-
    explored state whose *only* recorded row entry is the exact reverse of
    a well-learned neighbouring state's own best move — greedy inference
    then walks back and forth between the two forever, since neither ever
    looks locally wrong from its own row alone. Scans `ranked` for the
    first legal entry that ISN'T the exact reverse of `last_direction`,
    but remembers the first legal reverse-direction candidate as a
    fallback — used only if no better legal option exists, so a real dead
    end still allows backtracking rather than forcing `STAY` unnecessarily.
    Returns `None` only if nothing in `ranked` is legal at all."""
    fallback = None
    avoid = opposite_direction(last_direction)
    for action in ranked:
        if action not in legal:
            continue
        if action == avoid and fallback is None:
            fallback = action
            continue
        return action
    return fallback


def pick_ranked_action_avoiding_backtrack(
    ranked: list[str], own_pos: Position, board: Board, barriers: BarrierSet, last_direction: str | None
) -> str | None:
    """Like `pick_avoiding_backtrack`, but for `RLCopBrain._decide_move`'s
    mixed move-or-barrier action space: a `"BARRIER_<dir>"` candidate is
    checked via `BarrierSet.can_place` and, if legal, wins immediately —
    never subject to backtrack-avoidance, since only real movement can
    literally reverse a step. A move candidate goes through the same
    remember-the-first-legal-reverse-as-fallback logic
    `pick_avoiding_backtrack` uses. Returns the winning token from `ranked`
    verbatim, or `None` if nothing in it is legal at all.

    **Self-trap guard** (found live: a real match's Q-table walled off 3 of
    the cop's own 4 neighbours across several separate turns — each
    individual placement was "legal" in isolation — then froze on STAY for
    19 straight rounds once boxed in). Two checks, mirroring `CopBrain`'s
    own barrier exclusion (`cop_brain.py::_decide_move`'s docstring) but
    made explicit here since the RL ranking has no equivalent structural
    guarantee on its own:
    1. Never place on the direction the ranking would otherwise have moved
       in (`preferred_move`) — the same "not the cop's own preferred next
       step" rule `CopBrain` already applies.
    2. Never place a barrier that would leave literally zero legal
       neighbours open — the direct `thief_has_no_legal_move` check
       `CopBrain`'s own docstring says was proven redundant *there* (rule 1
       above already covers it structurally for a fresh greedy pick every
       turn) but isn't redundant here, since nothing else in this ranked,
       already-multi-turn-committed path proves the same. Reused generically
       (same precedent `CopBrain`'s docstring names): it's a pure
       "is every orthogonal neighbour blocked" predicate, not thief-specific.
    A barrier candidate that fails either check is skipped, not treated as
    illegal — scanning continues to the next-ranked action exactly like an
    physically-illegal candidate does."""
    legal_move_directions = legal_directions(own_pos, board, barriers)
    preferred_move = next((a for a in ranked if a in legal_move_directions and a != "STAY"), None)
    avoid = opposite_direction(last_direction)
    move_fallback: str | None = None
    for action in ranked:
        if action.startswith("BARRIER_"):
            direction = action.removeprefix("BARRIER_")
            if direction == preferred_move:
                continue
            candidate = own_pos + DELTAS[direction]
            if not barriers.can_place(own_pos, candidate, board):
                continue
            hypothetical = BarrierSet(quota=barriers.quota, placed=barriers.placed | {candidate})
            if thief_has_no_legal_move(own_pos, board, hypothetical):
                continue
            return action
        if action not in legal_move_directions:
            continue
        if action == avoid and move_fallback is None:
            move_fallback = action
            continue
        return action
    return move_fallback
