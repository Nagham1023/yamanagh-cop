"""BeliefTracker: `SelfPlayEnv`'s own scent/belief bookkeeping (PRD 14 sub-
layer A) — split out of `env.py` once that file grew past the 150-line
house cap.

Wraps the exact two objects a real turn updates (`cop.memory.scent.ScentField`,
`cop.memory.belief.BeliefMap`), advanced in the exact order
`orchestrator_turn.py::take_turn` uses: zero out newly-placed barriers,
advance the scent field, fold it into belief. `SelfPlayEnv` calls `advance()`
once per step (only when the episode continues — see its own docstring) and
reads `believed_target()` to encode state; it never touches `ScentField`/
`BeliefMap` directly.

**Deliberately not simulated here**: `BeliefMap.update_from_hint`/
`update_from_scent_map` — the two channels driven by an actual peer's own
hint text and scent map. `SelfPlayEnv` has no peer, so there is no honest
data to feed either from; fabricating one (e.g. from the true `thief_pos`)
would leak ground truth back into the belief the policy is supposed to
learn to act under uncertainty about. Consequence, stated plainly: the
trained policy sees belief distributions that are *more uncertain on
average* than a real match's (which gets two extra corroborating signals
this tracker doesn't simulate) — a conservative bias, not a dangerous one,
but a real, documented gap between this training distribution and
inference.
"""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.memory.belief import BeliefMap
from cop.memory.scent import ScentField
from cop.shared.config import GameConfig


class BeliefTracker:
    def __init__(self, board: Board, game_config: GameConfig, barriers: BarrierSet) -> None:
        self._board = board
        self._game_config = game_config
        self._barriers = barriers
        self.scent_field = ScentField.from_config(game_config)
        self.belief_map = BeliefMap.uniform(board, barriers=barriers)

    def reset(self) -> None:
        self.scent_field = ScentField.from_config(self._game_config)
        self.belief_map = BeliefMap.uniform(self._board, barriers=self._barriers)

    def advance(self, cop_pos: Position) -> None:
        """Re-sync belief with any newly-placed barrier, decay+deposit this
        turn's scent, then fold it into belief — the same three real calls,
        same order, a live turn makes."""
        self.belief_map.zero_out_barriers(self._barriers)
        self.scent_field.advance(cop_pos, self._board)
        self.belief_map.update_from_scent(self.scent_field, cop_pos, self._board)

    def believed_target(self) -> tuple[Position, float]:
        """The belief's own best guess, and how confident it is in that
        guess — exactly the two values `rl_state_encoding.encode_state`'s
        `target_pos`/`belief_confidence` parameters need."""
        believed_pos = self.belief_map.most_likely_cell()
        return believed_pos, self.belief_map.probability(believed_pos)
