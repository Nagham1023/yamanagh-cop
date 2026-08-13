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

**PRD 14 sub-layer A** — `belief_entropy_provider`: a seam, not wiring.
`training/env.py::SelfPlayEnv` now trains against a belief-based state
(see its own docstring); this constructor accepts an optional callable
supplying the *same* signal at real-match inference time, mirroring the
"seam now, plug in later" shape `reasoning/state.py::ground_truth_target_position`
already established for `target_pos` itself. Deliberately left unbound by
any real caller for now (confirmed decision, not an oversight) — every real
match / `run_local_subgame` use gets the default `0.0` (zero entropy, exact
for a point-mass distribution — the same maximal-certainty case ground-
truth training always represents), so this file's own change is inert in
production until a future, separately-scoped PRD does the one-line
`Orchestrator` wiring. Same "built, tested, and left inert for now" posture
PRD 11 itself already used for the whole class.

**PRD 14 round-2 post-gate** — `second_mode_provider`: a second, parallel
seam, identical posture to `belief_entropy_provider` above. Every real
match / `run_local_subgame` use gets the default `None` (no second belief
mode at inference time), so this addition is inert in production too.

**PRD 14 round-2 post-gate — the backtrack guard**: found by running a real
promoted checkpoint against a real opponent — a sparsely-explored state's
only row entry can be the exact reverse of a neighbour's own best move, so
greedy inference cycles between the two forever (`rl_legal_directions.
pick_avoiding_backtrack`'s docstring has the full story). `_last_direction`
is per-instance, per-match state — every real caller already constructs a
fresh `RLCopBrain` per episode/match."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..domain.movement import DELTAS
from .brain_base import Action, Move, PlaceBarrier
from .cop_brain import CopBrain
from .rl_checkpoint import RLQTable, load_checkpoint
from .rl_legal_directions import legal_directions as _legal_directions
from .rl_legal_directions import pick_avoiding_backtrack, pick_ranked_action_avoiding_backtrack
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
        belief_entropy_provider: Callable[[], float] | None = None,
        second_mode_provider: Callable[[], Position | None] | None = None,
    ) -> None:
        """Loads a checkpoint if one exists at `checkpoint_path`; otherwise
        `self._q_table` stays `None` and every decision falls through to
        `CopBrain`'s own heuristic — see the class docstring.
        `belief_entropy_provider`/`second_mode_provider` — see the module
        docstring."""
        self._q_table: RLQTable | None = self._load_or_none(checkpoint_path)
        self._belief_entropy_provider = belief_entropy_provider
        self._second_mode_provider = second_mode_provider
        self._last_direction: str | None = None

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

    def _belief_entropy(self) -> float:
        return self._belief_entropy_provider() if self._belief_entropy_provider else 0.0

    def _second_mode(self) -> Position | None:
        return self._second_mode_provider() if self._second_mode_provider else None

    def _pick_move(
        self, own_pos: Position, target_pos: Position, board: Board, barriers: BarrierSet
    ) -> str:
        """Q-table ranking first, legality-masked; `CopBrain`'s heuristic on
        any miss (no checkpoint, or a state training never visited)."""
        if self._q_table is not None:
            state = encode_state(
                own_pos, target_pos, board, barriers,
                belief_entropy=self._belief_entropy(), second_mode_pos=self._second_mode(),
            )
            ranked = self._q_table.ranked_actions(state)
            if ranked is not None:
                legal = _legal_directions(own_pos, board, barriers)
                action = pick_avoiding_backtrack(ranked, legal, self._last_direction)
                if action is not None:
                    self._last_direction = action
                    return action
                self._last_direction = None
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
                own_pos, target_pos, board, barriers,
                belief_entropy=self._belief_entropy(), second_mode_pos=self._second_mode(),
            )
            ranked = self._q_table.ranked_actions(state)
            if ranked is not None:
                action = pick_ranked_action_avoiding_backtrack(
                    ranked, own_pos, board, barriers, self._last_direction
                )
                if action is not None and action.startswith("BARRIER_"):
                    direction = action.removeprefix("BARRIER_")
                    return PlaceBarrier(target=own_pos + DELTAS[direction])
                if action is not None:
                    self._last_direction = action
                    return Move(direction=action)
                self._last_direction = None
                return Move(direction="STAY")
        return super()._decide_move(own_pos, target_pos, board, barriers)
