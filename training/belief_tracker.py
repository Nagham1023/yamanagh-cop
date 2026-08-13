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

**Now simulated (post-gate follow-up)**: `BeliefMap.update_from_scent_map`
— the thief's own real scent trail, un-lie-able by construction in the real
protocol (`Intent` never applies to this channel; ch. 4.4's own worked
example reads this data as always-truthful corroboration). A real match's
cop genuinely receives this every turn (`orchestrator_turn.take_turn`'s
`request_scent_map_from_peer`); `SelfPlayEnv` simply never simulated it
before this — not a fabrication of untrustworthy data, since there's
nothing to fabricate: this channel is honest in the real protocol too, so
simulating it faithfully in training completes an already-decided
realistic simulation rather than leaking anything.

**Now also simulated**: `BeliefMap.update_from_hint`, via a synthetic thief
hint (`fold_synthetic_hint`) — unlike the scent channel this genuinely can
lie (`Intent`), so training now also teaches the cop to weigh hint evidence
against the always-truthful scent corroboration above, the exact
protection `update_from_hint`'s own docstring already names. Uses only
`TemplateHintProvider` (zero-cost, deterministic) — never an LLM-backed
provider — and a caller-supplied `rng` that must be a single stream living
for the whole training run, not reseeded per episode (see `train_loop.py`'s
own construction site) — a fresh stream every episode would let the
policy learn a spurious "step N hints are always lies" artifact of the
simulator's own RNG lifetime instead of a generalizable skill.

Both channels are approximations of an unknown real opponent's actual
behavior, not a claim of zero training/inference gap — a smaller sim-to-
real gap than before this change, not a zero one.
"""

from __future__ import annotations

import random

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.memory.belief import BeliefMap
from cop.memory.scent import ScentField
from cop.reasoning.hint import decide_intent, generate_hint, interpret_hint
from cop.shared.config import GameConfig
from cop.tools.hint_providers import TemplateHintProvider


class BeliefTracker:
    def __init__(
        self, board: Board, game_config: GameConfig, barriers: BarrierSet, rng: random.Random
    ) -> None:
        self._board = board
        self._game_config = game_config
        self._barriers = barriers
        self._rng = rng
        self._hint_provider = TemplateHintProvider()
        self.scent_field = ScentField.from_config(game_config)
        self.peer_scent_field = ScentField.from_config(game_config)
        self.belief_map = BeliefMap.uniform(board, barriers=barriers)

    def reset(self) -> None:
        self.scent_field = ScentField.from_config(self._game_config)
        self.peer_scent_field = ScentField.from_config(self._game_config)
        self.belief_map = BeliefMap.uniform(self._board, barriers=self._barriers)

    def advance(self, cop_pos: Position) -> None:
        """Re-sync belief with any newly-placed barrier, decay+deposit this
        turn's scent, then fold it into belief — the same three real calls,
        same order, a live turn makes."""
        self.belief_map.zero_out_barriers(self._barriers)
        self.scent_field.advance(cop_pos, self._board)
        self.belief_map.update_from_scent(self.scent_field, cop_pos, self._board)

    def fold_peer_scent(self, thief_pos: Position) -> None:
        """Simulates receiving the thief's own real scent map — deposit
        this round's scent at its (post-this-round-move) position, then
        fold the whole field into belief via the same always-truthful
        channel a real peer exchange uses."""
        self.peer_scent_field.advance(thief_pos, self._board)
        self.belief_map.update_from_scent_map(self.peer_scent_field.full_field(), self._board)

    def fold_synthetic_hint(self, thief_pos: Position, lie_probability: float) -> None:
        """Generates a hint *about* `thief_pos` — mirroring exactly what
        `orchestrator_turn.take_turn` does for the cop's own outgoing hint,
        each peer describing its own true position — then folds it into
        belief exactly as `update_from_hint` already does for a real
        received hint. `update_from_hint` never knows or cares whether the
        result was a lie; `decide_intent`/`lie_probability` decide that
        before generation, the same split a real turn already has."""
        intent = decide_intent(lie_probability, self._rng)
        text = generate_hint(thief_pos, self._hint_provider, self._game_config, intent)
        focal_point = interpret_hint(text, self._board)
        self.belief_map.update_from_hint(focal_point, self._board)

    def believed_target(self) -> tuple[Position, float]:
        """The belief's own best guess, and the whole distribution's
        Shannon entropy (PRD 14 post-gate: replaced peak probability) —
        exactly the two values `rl_state_encoding.encode_state`'s
        `target_pos`/`belief_entropy` parameters need."""
        believed_pos = self.belief_map.most_likely_cell()
        return believed_pos, self.belief_map.entropy()

    def believed_targets(self) -> tuple[Position, float, Position | None]:
        """`believed_target()` plus an optional second belief mode (PRD 14
        round-2 post-gate: bimodal state enrichment) — `(primary, entropy,
        second_mode_or_None)`. `believed_target()` itself stays unchanged so
        the existing single-target inference seam (`RLCopBrain`'s own
        `belief_entropy_provider`/`target_pos` usage) is untouched by this
        addition."""
        primary = self.belief_map.most_likely_cell()
        entropy = self.belief_map.entropy()
        second = self.belief_map.second_mode(primary)
        return primary, entropy, second
