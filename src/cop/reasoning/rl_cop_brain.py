"""RLCopBrain: tabular-Q-learning movement policy (PRD 11), `CopBrain` otherwise.

**PRD 14 sub-layer B**: `_decide_move` is now also overridden — the Q-table
drives the barrier-vs-move choice too, not just movement (barrier RL was
PRD 11's own "explicitly out of scope" call, reversed deliberately once
`training/env.py` started simulating barrier placement for real). On a
state training never visited, this falls back to `CopBrain`'s heuristic
rather than guessing: the RL brain can never be worse than "no RL at all"
outside its training distribution.

The raw Q-table ranking is never trusted directly (rule 25/I7): every
ranked action is re-checked live — a move against a Python-computed legal
set, a barrier against `BarrierSet.can_place` — before anything returns.

**PRD 14 sub-layer A** — `belief_confidence_provider`: a seam, not wiring.
`training/env.py::SelfPlayEnv` now trains against a belief-based state
(see its own docstring); this constructor accepts an optional callable
supplying the *same* signal at real-match inference time, mirroring the
"seam now, plug in later" shape `reasoning/state.py::ground_truth_target_position`
already established for `target_pos` itself. Deliberately left unbound by
any real caller for now (confirmed decision, not an oversight) — every real
match / `run_local_subgame` use gets the default `1.0` (maximal confidence,
the same bucket ground-truth training used before sub-layer A existed), so
this file's own change is inert in production until a future, separately-
scoped PRD does the one-line `Orchestrator` wiring. Same "built, tested,
and left inert for now" posture PRD 11 itself already used for the whole
class.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..domain.movement import DELTAS, apply_move
from .brain_base import Action, Move, PlaceBarrier
from .cop_brain import CopBrain
from .rl_checkpoint import RLQTable, load_checkpoint
from .rl_state_encoding import encode_state

DEFAULT_CHECKPOINT_PATH = "training/promoted/rl_cop_qtable.json"


class RLCopBrain(CopBrain):
    """A missing or unreadable checkpoint at construction time is not an
    error — it means "behave exactly like `CopBrain`," which is the correct,
    safe default before a checkpoint has ever been promoted (PRD 13)."""

    def __init__(
        self,
        checkpoint_path: str | Path = DEFAULT_CHECKPOINT_PATH,
        *,
        belief_confidence_provider: Callable[[], float] | None = None,
    ) -> None:
        """Loads a checkpoint if one exists at `checkpoint_path`; otherwise
        `self._q_table` stays `None` and every decision falls through to
        `CopBrain`'s own heuristic — see the class docstring.
        `belief_confidence_provider` — see the module docstring."""
        self._q_table: RLQTable | None = self._load_or_none(checkpoint_path)
        self._belief_confidence_provider = belief_confidence_provider

    @staticmethod
    def _load_or_none(path: str | Path) -> RLQTable | None:
        """Swallows exactly the two failure shapes `load_checkpoint` itself
        raises for "no usable checkpoint here" (missing file, malformed
        content) — anything else propagates, since that would signal a bug
        elsewhere, not an expected pre-promotion state."""
        try:
            return load_checkpoint(path)
        except (FileNotFoundError, ValueError):
            return None

    def _belief_confidence(self) -> float:
        return self._belief_confidence_provider() if self._belief_confidence_provider else 1.0

    def _pick_move(
        self, own_pos: Position, target_pos: Position, board: Board, barriers: BarrierSet
    ) -> str:
        """Q-table ranking first, legality-masked; `CopBrain`'s heuristic on
        any miss (no checkpoint, or a state training never visited)."""
        if self._q_table is not None:
            state = encode_state(
                own_pos, target_pos, board, barriers, belief_confidence=self._belief_confidence()
            )
            ranked = self._q_table.ranked_actions(state)
            if ranked is not None:
                legal = _legal_directions(own_pos, board, barriers)
                for action in ranked:
                    if action in legal:
                        return action
                return "STAY"
        return super()._pick_move(own_pos, target_pos, board, barriers)

    def _decide_move(
        self, own_pos: Position, target_pos: Position, board: Board, barriers: BarrierSet
    ) -> Action:
        """Q-table ranking over the full move-or-barrier action set,
        legality-rechecked action by action; `CopBrain`'s full heuristic
        (barrier choice included) only on a genuine table miss
        (`ranked is None`). A recognized-but-exhausted state (every ranked
        action fails its live recheck) resolves to `Move("STAY")` instead —
        matching `_pick_move`'s own precedent: once the table recognizes a
        state at all, staying in-table beats switching brains mid-decision."""
        if self._q_table is not None:
            state = encode_state(
                own_pos, target_pos, board, barriers, belief_confidence=self._belief_confidence()
            )
            ranked = self._q_table.ranked_actions(state)
            if ranked is not None:
                legal_directions = _legal_directions(own_pos, board, barriers)
                for action in ranked:
                    if action.startswith("BARRIER_"):
                        direction = action.removeprefix("BARRIER_")
                        candidate = own_pos + DELTAS[direction]
                        if barriers.can_place(own_pos, candidate, board):
                            return PlaceBarrier(target=candidate)
                        continue
                    if action in legal_directions:
                        return Move(direction=action)
                return Move(direction="STAY")
        return super()._decide_move(own_pos, target_pos, board, barriers)


def _legal_directions(own_pos: Position, board: Board, barriers: BarrierSet) -> set[str]:
    """Every direction whose destination is on-board and unblocked, plus
    `STAY` (always legal) — the same check `CopBrain._pick_move` already
    performs per-candidate, computed once here as a set for the ranked-list
    intersection above."""
    legal = {"STAY"}
    for direction in DELTAS:
        if direction == "STAY":
            continue
        destination = apply_move(own_pos, direction, board)
        if destination is not None and not barriers.blocks(destination):
            legal.add(direction)
    return legal
