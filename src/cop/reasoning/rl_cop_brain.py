"""RLCopBrain: tabular-Q-learning movement policy (PRD 11), `CopBrain` otherwise.

Overrides only `_pick_move` — `_decide_move`'s barrier heuristic is
inherited unchanged from `CopBrain` (barrier RL is explicitly out of scope,
see `PRD/PRD-11-rl-training-simulator.md`). On a state the training run
never visited — including any state where a real barrier sits adjacent,
since self-play training never places one, see `training/env.py` — this
falls back to the inherited `CopBrain` heuristic rather than guessing: the
RL brain can never be worse than "no RL at all" outside its training
distribution.

The raw Q-table ranking is never trusted directly (rule 25 / I7): it is
always intersected with a Python-computed legal-move set, reusing the same
`domain.movement` primitives `CopBrain` itself uses, before anything is
returned.
"""

from __future__ import annotations

from pathlib import Path

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..domain.movement import DELTAS, apply_move
from .cop_brain import CopBrain
from .rl_checkpoint import RLQTable, load_checkpoint
from .rl_state_encoding import encode_state

DEFAULT_CHECKPOINT_PATH = "training/promoted/rl_cop_qtable.json"


class RLCopBrain(CopBrain):
    """A missing or unreadable checkpoint at construction time is not an
    error — it means "behave exactly like `CopBrain`," which is the correct,
    safe default before a checkpoint has ever been promoted (PRD 13)."""

    def __init__(self, checkpoint_path: str | Path = DEFAULT_CHECKPOINT_PATH) -> None:
        """Loads a checkpoint if one exists at `checkpoint_path`; otherwise
        `self._q_table` stays `None` and every decision falls through to
        `CopBrain`'s own heuristic — see the class docstring."""
        self._q_table: RLQTable | None = self._load_or_none(checkpoint_path)

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

    def _pick_move(
        self, own_pos: Position, target_pos: Position, board: Board, barriers: BarrierSet
    ) -> str:
        """Q-table ranking first, legality-masked; `CopBrain`'s heuristic on
        any miss (no checkpoint, or a state training never visited)."""
        if self._q_table is not None:
            state = encode_state(own_pos, target_pos, board, barriers)
            ranked = self._q_table.ranked_actions(state)
            if ranked is not None:
                legal = _legal_directions(own_pos, board, barriers)
                for action in ranked:
                    if action in legal:
                        return action
                return "STAY"
        return super()._pick_move(own_pos, target_pos, board, barriers)


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
