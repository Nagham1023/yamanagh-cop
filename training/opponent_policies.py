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
