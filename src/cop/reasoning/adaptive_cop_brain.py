"""AdaptiveCopBrain (PLAN.md Stage 11.4): escape-area-aware pursuit with a
pessimistic one-ply thief reply, replacing `CopBrain`'s raw Manhattan-
distance greed. Selectable via
`[strategy] police_class = "cop.reasoning.adaptive_cop_brain:AdaptiveCopBrain"`
-- same dotted-path switch `RLCopBrain`'s own promotion already used, so
this ships alongside the existing brains rather than replacing the default.

Why: a pure distance-closing pursuer never catches a distance-maximizing
evader on an open board -- once distance parity is reached there is no
gradient left to close it (confirmed live this project's own real matches,
and independently by published third-party research read for context, not
copied). The real lever is shrinking the opponent's own reachable world
(`reasoning/escape_area.py`), scored *pessimistically* -- against the
thief's best possible reply, not its average one -- so the cop never walks
into a move that looks good only because the thief cooperates.

Non-determinism (PLAN.md Stage 11.2c): candidates within `_TIE_MARGIN` of
the best score are sampled via softmax rather than a fixed tie-break, so
behaviour isn't perfectly repeatable match to match. This is move-selection
randomness only, drawn from `self._rng` (a plain `random.Random`) -- never
the commit-reveal nonce, which stays `secrets`-based and untouched by this
class entirely.
"""

from __future__ import annotations

import math
import random

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..domain.movement import DELTAS, apply_move
from .brain_base import Action, Move, PlaceBarrier
from .cop_brain import CopBrain
from .escape_area import escape_area

_TIE_MARGIN = 1e-6
_SOFTMAX_TEMPERATURE = 0.75


def _thief_pessimistic_area(target_pos: Position, board: Board, barriers: BarrierSet, radius: int) -> int:
    """The thief's own best-case escape area one ply after `target_pos`,
    assuming it plays its own best reply (maximizing its area) rather than
    staying put -- the "pessimistic" half of the search. Falls back to
    staying in place if every neighbour is blocked."""
    best = escape_area(target_pos, board, barriers, radius)
    for delta in DELTAS.values():
        if delta == Position(0, 0):
            continue
        neighbor = target_pos + delta
        if not board.in_bounds(neighbor) or barriers.blocks(neighbor):
            continue
        best = max(best, escape_area(neighbor, board, barriers, radius))
    return best


class AdaptiveCopBrain(CopBrain):
    def __init__(
        self,
        *,
        area_radius: int = 4,
        area_weight: float = 3.0,
        barrier_base_cost: float = 4.0,
        barrier_endgame_cost: float = 0.5,
        endgame_area: int = 12,
        rng: random.Random | None = None,
    ) -> None:
        self._area_radius = area_radius
        self._area_weight = area_weight
        self._barrier_base_cost = barrier_base_cost
        self._barrier_endgame_cost = barrier_endgame_cost
        self._endgame_area = endgame_area
        self._rng = rng or random.Random()

    def _softmax_pick(self, scored: list[tuple[float, object]]) -> object:
        """Among candidates within `_TIE_MARGIN` of the best score, sample
        by softmax instead of always taking the same one -- see this
        module's own docstring for why. A single candidate (or a single
        clear winner) returns deterministically; only genuine near-ties
        introduce variety."""
        if not scored:
            return None
        best_score = max(score for score, _ in scored)
        tied = [(score, item) for score, item in scored if score >= best_score - _TIE_MARGIN]
        if len(tied) == 1:
            return tied[0][1]
        weights = [math.exp(score / _SOFTMAX_TEMPERATURE) for score, _ in tied]
        total = sum(weights)
        pick = self._rng.random() * total
        cumulative = 0.0
        for weight, (_, item) in zip(weights, tied, strict=True):
            cumulative += weight
            if pick <= cumulative:
                return item
        return tied[-1][1]

    def _pick_move(
        self, own_pos: Position, target_pos: Position, board: Board, barriers: BarrierSet
    ) -> str:
        """Score each legal move by the thief's pessimistic reply area
        after it (lower is better for the cop) minus the residual
        distance, softmax-picked among near-ties."""
        scored: list[tuple[float, str]] = []
        for direction in DELTAS:
            destination = apply_move(own_pos, direction, board)
            if destination is None or barriers.blocks(destination):
                continue
            distance = abs(destination.col - target_pos.col) + abs(destination.row - target_pos.row)
            thief_area = _thief_pessimistic_area(target_pos, board, barriers, self._area_radius)
            score = -self._area_weight * thief_area - distance
            scored.append((score, direction))
        picked = self._softmax_pick(scored)
        return picked if picked is not None else "STAY"

    def _decide_move(
        self, own_pos: Position, target_pos: Position, board: Board, barriers: BarrierSet
    ) -> Action:
        """A barrier is worth playing only when it shrinks the thief's own
        pessimistic escape area by more than its (economy-adjusted) cost;
        otherwise falls back to `_pick_move`. Barrier quota gets cheaper
        once the thief's world has already shrunk below `endgame_area` --
        early-game walls on a wide-open board rarely pay for themselves,
        late-game ones close out a capture."""
        current_area = _thief_pessimistic_area(target_pos, board, barriers, self._area_radius)
        cost = self._barrier_endgame_cost if current_area <= self._endgame_area else self._barrier_base_cost

        best_barrier: Position | None = None
        best_gain = 0.0
        for delta in DELTAS.values():
            if delta == Position(0, 0):
                continue
            candidate = own_pos + delta
            if not barriers.can_place(own_pos, candidate, board):
                continue
            trial = BarrierSet(quota=barriers.quota, placed=set(barriers.placed) | {candidate})
            new_area = _thief_pessimistic_area(target_pos, board, trial, self._area_radius)
            gain = (current_area - new_area) - cost
            if gain > best_gain:
                best_gain = gain
                best_barrier = candidate

        if best_barrier is not None:
            return PlaceBarrier(target=best_barrier)
        direction = self._pick_move(own_pos, target_pos, board, barriers)
        return Move(direction=direction)
