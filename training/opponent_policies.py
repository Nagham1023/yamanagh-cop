"""Synthetic self-play sparring opponents (PRD 11) — plain functions only,
matching `subgame.py`'s `ThiefMover` shape (`(Position, Board, BarrierSet)
-> str`). Never a `BrainBase`/`ThiefBrain` subclass; never imported by
anything under `src/cop/` (see `training/__init__.py`'s own docstring for
the full boundary rationale).

`greedy_escape_thief` is a **deliberate duplication** of
`tests/support/greedy_thief_mover.py::greedy_thief_move`, not an import of
it: (1) `tests/` is test scaffolding, not a stable internal API — coupling
training to it means a test refactor could silently break a training run;
(2) it keeps "training never imports from `tests/`" as unambiguous as
"training never imports from `src/cop/`". The duplication is ~20 lines,
the same kind of small, load-bearing repetition this repo already accepts
elsewhere for isolation (PRD-3's own Design Question 5).
"""

from __future__ import annotations

import random
from collections.abc import Callable

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.domain.movement import DELTAS, apply_move
from cop.memory.scent import ScentField
from cop.shared.config import GameConfig

ThiefMover = Callable[[Position, Board, BarrierSet], str]

_TIE_BREAK_ORDER = ("N", "E", "S", "W")


def make_random_walk_thief(rng: random.Random) -> ThiefMover:
    """Curriculum stage 0: uniform choice among legal moves, seeded — the
    weakest opponent, so early Q-values form over an easy, low-variance
    target before the harder stage-1 opponent is introduced."""

    def _mover(own_pos: Position, board: Board, barriers: BarrierSet) -> str:
        legal = _legal_directions(own_pos, board, barriers)
        return rng.choice(legal) if legal else "STAY"

    return _mover


def greedy_escape_thief(own_pos: Position, board: Board, barriers: BarrierSet) -> str:
    """Curriculum stage 1: prefers the neighbour with the most open
    orthogonal neighbours of its own (an escape-route count) — the same
    algorithm `tests/support/greedy_thief_mover.py` implements, and
    `PRD-3-blind-strategy.md`'s own "also verify" framing for what a
    reasonable thief-side stand-in should do."""
    candidates: list[tuple[int, str]] = []
    for direction in _TIE_BREAK_ORDER:
        destination = apply_move(own_pos, direction, board)
        if destination is None or barriers.blocks(destination):
            continue
        candidates.append((_count_open_neighbours(destination, board, barriers), direction))
    if not candidates:
        return "STAY"
    return max(candidates, key=lambda pair: pair[0])[1]


def lookahead_evader_thief(own_pos: Position, board: Board, barriers: BarrierSet) -> str:
    """Curriculum stage 2 (PRD 14): depth-2 escape-route lookahead — scores
    each candidate first move by the *best* second-move open-neighbour count
    reachable from there, not just the first move's own immediate openness
    the way `greedy_escape_thief` does. Ties break on immediate openness,
    the same criterion stage 1 uses alone.

    Deliberately does not, and structurally cannot, react to the cop's own
    position: `ThiefMover`'s own signature — `(own_pos, board, barriers) ->
    str` — never receives it, the same fog-of-war posture every opponent in
    this file already has (`SelfPlayEnv.step()`'s own call site confirms
    this: `self._opponent(self.thief_pos, self._board, self._barriers)`, no
    `cop_pos` argument exists to pass). A "distance the cop could close in
    reply" opponent would need that argument added to the whole `ThiefMover`
    interface — real scope beyond one new function — so this stage instead
    goes deeper on the one signal already available: its own future
    mobility, not the cop's position."""
    candidates: list[tuple[int, int, str]] = []
    for direction in _TIE_BREAK_ORDER:
        destination = apply_move(own_pos, direction, board)
        if destination is None or barriers.blocks(destination):
            continue
        immediate_openness = _count_open_neighbours(destination, board, barriers)
        second_ply_best = 0
        for second_direction in _TIE_BREAK_ORDER:
            second_destination = apply_move(destination, second_direction, board)
            if second_destination is None or barriers.blocks(second_destination):
                continue
            second_ply_best = max(
                second_ply_best, _count_open_neighbours(second_destination, board, barriers)
            )
        candidates.append((second_ply_best, immediate_openness, direction))
    if not candidates:
        return "STAY"
    return max(candidates, key=lambda triple: (triple[0], triple[1]))[2]


def make_scent_backtracking_thief(game_config: GameConfig, rng: random.Random) -> ThiefMover:
    """Curriculum stage 3 (PRD 14 round-2 post-gate): prefers cells where
    ITS OWN scent is already strong — deliberately backtracks into its
    recent trail or lingers where that trail has only partially decayed —
    to stress-test whether the cop's belief system can tell fresh presence
    from stale residue, rather than a thief that (like every other stage)
    simply never revisits itself. Owns its own `ScentField` via closure,
    exactly like `make_random_walk_thief` owns its own `rng` — no
    `ThiefMover` signature change, no new call-site plumbing anywhere.

    **Must be rebuilt fresh every episode when this stage is active** — the
    inverse of `belief_tracker.py`'s own RNG-lifetime lesson: there, a
    stream reused across episodes was required; here, a `ScentField` reused
    across episodes would let "old trail" accumulate across unrelated
    games, corrupting the training distribution. See `train_loop.py`'s own
    construction site — this factory is deliberately NOT built once outside
    the episode loop the way the other three stage-movers are."""
    own_scent = ScentField.from_config(game_config)

    def _mover(own_pos: Position, board: Board, barriers: BarrierSet) -> str:
        own_scent.advance(own_pos, board)
        legal = _legal_directions(own_pos, board, barriers)
        if not legal:
            return "STAY"
        field = own_scent.full_field()
        scored = [(field.get(apply_move(own_pos, d, board), 0.0), d) for d in legal]
        best_score = max(score for score, _ in scored)
        best = [d for score, d in scored if score == best_score]
        return rng.choice(best)

    return _mover


def _legal_directions(own_pos: Position, board: Board, barriers: BarrierSet) -> list[str]:
    legal = []
    for direction in _TIE_BREAK_ORDER:
        destination = apply_move(own_pos, direction, board)
        if destination is not None and not barriers.blocks(destination):
            legal.append(direction)
    return legal


def _count_open_neighbours(pos: Position, board: Board, barriers: BarrierSet) -> int:
    count = 0
    for direction, delta in DELTAS.items():
        if direction == "STAY":
            continue
        neighbour = pos + delta
        if board.in_bounds(neighbour) and not barriers.blocks(neighbour):
            count += 1
    return count
