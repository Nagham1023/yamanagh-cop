"""Minimal Thief-role move chooser for std_v1 role alternation (spec
Section 6: sub-games 2/4/6 flip this repo into the opposite of its
natural Police role). Deliberately simple evasion -- legal and
spec-compliant, not a second real strategy investment; this repo's own
strategy work is entirely on the Cop side (PRD 3+). Never reached
outside std_v1's own alternated sub-games.
"""

from __future__ import annotations

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..domain.movement import apply_move


def believed_cop_cell(scent: dict[Position, float], fallback: Position) -> Position:
    """The highest-intensity reported cell in the Police's own last
    `smell_grid`, or `fallback` (the terms' own public `cop_start`)
    before anything has been sensed yet."""
    if not scent:
        return fallback
    return max(scent, key=scent.get)


def _distance(a: Position, b: Position) -> int:
    return abs(a.col - b.col) + abs(a.row - b.row)


def choose_thief_move(board: Board, position: Position, barriers: BarrierSet, threat: Position) -> str:
    """Greedy evasion: the legal move that most increases Manhattan
    distance from `threat`; "STAY" when nothing improves on staying put."""
    best_direction = "STAY"
    best_distance = _distance(position, threat)
    for direction in ("N", "S", "E", "W"):
        destination = apply_move(position, direction, board)
        if destination is None or barriers.blocks(destination):
            continue
        distance = _distance(destination, threat)
        if distance > best_distance:
            best_distance = distance
            best_direction = direction
    return best_direction
