"""WeightedRLCopBrain: a fixed-probability router between `RLCopBrain` and
`CopBrain` — `_RL_WEIGHT` (90%) of decisions go to the RL policy, the rest
to the plain heuristic.

Found live: a real match's plain `CopBrain` got stuck oscillating E/W
between two adjacent cells for 26 straight rounds (steps 10-35 of a 35-step
game) and never got near the thief. Root cause: `_pick_move`'s greedy
Manhattan-distance descent has no lookahead, so once its belief target
settles into a near-tie between two neighbouring cells it has no way to
break out — its own docstring already names this exact failure mode.
`RLCopBrain._pick_move` already carries a real fix for it
(`rl_legal_directions.pick_avoiding_backtrack`, added post-PRD-14 after the
identical symptom showed up against a real opponent) — leaning most
decisions on the RL policy directly targets the observed bug rather than
inventing a new anti-oscillation mechanism from scratch.

Distinct from `HybridCopBrain` (entropy-gated: heuristic when the belief
map is confident, RL only when unsure — solving `ml-promotion-gate`'s own,
different tension between the two brains' raw capture rates). This router
is a fixed weighting regardless of confidence, chosen per decision, not
per game — and needs no bound `belief_entropy_provider` to do something
useful, since `RLCopBrain` already falls back to `CopBrain` per-decision on
any state its table never saw.

`_RL_WEIGHT = 0.9` is an algorithm-implementation constant, not an
Appendix F quantity (I6 doesn't apply — same category as `belief.py`'s
`_HINT_RELIABILITY`): the requested 90/10 split, not a derived or
negotiated game rule.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from pathlib import Path

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from .brain_base import Action, BrainBase
from .cop_brain import CopBrain
from .rl_cop_brain import DEFAULT_CHECKPOINT_PATH, RLCopBrain

_RL_WEIGHT = 0.9


class WeightedRLCopBrain(BrainBase):
    """Zero-arg construction (matching `RLCopBrain`/`HybridCopBrain` —
    `cli_peer_build.py` builds any `police_class` with no arguments). A
    missing/unpromoted checkpoint degrades exactly like `RLCopBrain` alone:
    every RL-routed decision silently falls through to `CopBrain`'s own
    heuristic, so this class is never worse than plain `CopBrain`, only
    ever better or equal.

    `random_source` is a seam for tests (same shape `belief_entropy_provider`
    already uses elsewhere in this package) — defaults to the real
    `random.random` for actual play.
    """

    def __init__(
        self,
        checkpoint_path: str | Path = DEFAULT_CHECKPOINT_PATH,
        *,
        belief_entropy_provider: Callable[[], float] | None = None,
        rl_weight: float = _RL_WEIGHT,
        random_source: Callable[[], float] = random.random,
    ) -> None:
        self._rl_brain = RLCopBrain(
            checkpoint_path=checkpoint_path, belief_entropy_provider=belief_entropy_provider
        )
        self._heuristic_brain = CopBrain()
        self._rl_weight = rl_weight
        self._random_source = random_source

    def _active_brain(self) -> BrainBase:
        """A fresh draw every call, not once per game — a single per-game
        coin flip would just replay either brain's own failure modes for
        the whole match instead of blending them."""
        return self._rl_brain if self._random_source() < self._rl_weight else self._heuristic_brain

    def _pick_move(
        self, own_pos: Position, target_pos: Position, board: Board, barriers: BarrierSet
    ) -> str:
        return self._active_brain()._pick_move(own_pos, target_pos, board, barriers)

    def _decide_move(
        self, own_pos: Position, target_pos: Position, board: Board, barriers: BarrierSet
    ) -> Action:
        return self._active_brain()._decide_move(own_pos, target_pos, board, barriers)
