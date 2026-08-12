"""HybridCopBrain: confidence-gated router between `CopBrain` and `RLCopBrain`
(PRD 14 post-gate follow-up).

`ml-promotion-gate` surfaced a real tension in the PRD 14 candidate: ground
truth, the RL policy captures less reliably than `CopBrain`'s own heuristic;
under belief-aware conditions (closer to a real match) it flips. This brain
is the obvious resolution — play the heuristic when the belief map is
actually confident, fall back to the RL policy only when genuinely unsure —
built and tested here, but **left completely unwired**, same "built, tested,
inert" posture `RLCopBrain` itself has held since PRD 11: no
`orchestrator_turn.py`, `cli_peer_build.py`, or `config/game.toml` change.
`cli_peer_build.py` constructs any `police_class` brain with zero arguments,
so pointing `police_class` at this class alone — without separate
`Orchestrator` plumbing to bind a real `belief_confidence_provider` — is not
sufficient for genuine hybrid behavior; that wiring is a future PRD's job,
not this one's.

Subclasses `BrainBase` directly, not `CopBrain`: this composes and delegates
to two independent, already-correct brains rather than inheriting one of
them — `isinstance(hybrid, CopBrain)` being true would be misleading given
most decisions may come from the Q-table path.

**Switch point**: reuses `rl_state_encoding.py`'s own `_CONFIDENCE_THRESHOLDS`/
`_bucket_confidence` rather than a new standalone magic number — bucket 3
("confident", `>= 0.6`) routes to `CopBrain`, anything lower routes to
`RLCopBrain`. Comparing via the real function rather than a re-derived
`>= 0.6` literal means this router's "is this confident" predicate
structurally can't drift from the Q-table's own bucketing even if the
comparison changes later.

**Shared-provider invariant**: the same `belief_confidence_provider` object
is passed straight through to the inner `RLCopBrain`, not wrapped or
re-derived — but it is genuinely called *twice* per decision when the unsure
branch is taken (once here to route, once inside `RLCopBrain`'s own
`_belief_confidence()`). Nothing in this class's synchronous call chain
mutates belief state between those two reads, so as long as the bound
provider is a plain, side-effect-free synchronous getter (the same shape
`RLCopBrain`'s own docstring already assumes), both reads are identical
within one turn — a testable invariant, not an unstated assumption.

**Rule 25/I7**: the router itself is a deterministic threshold comparison,
same category as `RLCopBrain`'s own `if self._q_table is not None` branch.
This class never constructs or mutates an `Action` itself — it only chooses
which already-legality-proven `_decide_move` to call, passing through the
same `(own_pos, target_pos, board, barriers)` unmodified. Legality is
inherited by construction from `CopBrain`'s and `RLCopBrain`'s own
independently-proven property sweeps, never re-verified at this layer.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from .brain_base import Action, BrainBase
from .cop_brain import CopBrain
from .rl_cop_brain import DEFAULT_CHECKPOINT_PATH, RLCopBrain
from .rl_state_encoding import _CONFIDENCE_THRESHOLDS, _bucket_confidence

_CONFIDENT_BUCKET = len(_CONFIDENCE_THRESHOLDS)  # the top bucket _bucket_confidence can return


class HybridCopBrain(BrainBase):
    """No provider bound -> `_is_confident()` always sees the same `1.0`
    default every other brain in this repo uses -> always routes to
    `CopBrain`, never touches the Q-table. Same "inert until wired" posture
    as `RLCopBrain` itself: even a mistaken `police_class` pointed at this
    class today would silently degrade to plain `CopBrain`, never crash or
    accidentally exercise the RL path."""

    def __init__(
        self,
        checkpoint_path: str | Path = DEFAULT_CHECKPOINT_PATH,
        *,
        belief_confidence_provider: Callable[[], float] | None = None,
    ) -> None:
        self._belief_confidence_provider = belief_confidence_provider
        self._confident_brain = CopBrain()
        self._unsure_brain = RLCopBrain(
            checkpoint_path=checkpoint_path,
            belief_confidence_provider=belief_confidence_provider,
        )

    def _is_confident(self) -> bool:
        confidence = self._belief_confidence_provider() if self._belief_confidence_provider else 1.0
        return _bucket_confidence(confidence) >= _CONFIDENT_BUCKET

    def _active_brain(self) -> BrainBase:
        return self._confident_brain if self._is_confident() else self._unsure_brain

    def _pick_move(
        self, own_pos: Position, target_pos: Position, board: Board, barriers: BarrierSet
    ) -> str:
        return self._active_brain()._pick_move(own_pos, target_pos, board, barriers)

    def _decide_move(
        self, own_pos: Position, target_pos: Position, board: Board, barriers: BarrierSet
    ) -> Action:
        return self._active_brain()._decide_move(own_pos, target_pos, board, barriers)
