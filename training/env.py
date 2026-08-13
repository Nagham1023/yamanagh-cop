"""SelfPlayEnv: step-based training environment over `domain/` primitives directly (PRD 11).

Deliberately not built on `reasoning/subgame.py::run_local_subgame`: that
function delegates to an already-decided `BrainBase._decide_move`, leaving
no way to inject the exploring action epsilon-greedy training needs to
choose itself. Reimplements the same physics shape directly instead;
`tests/unit/test_training_env_parity.py` proves the two stay physics-
identical (same outcome, same fixed policy/opponent) — regression-tested,
not assumed.

**PRD 14 sub-layer B**: barrier placement is simulated (PRD 11's original
"out of scope" call, reversed deliberately) — the cop's 4 orthogonal
neighbours, filtered through real `BarrierSet.can_place`, resolved via
`env_actions.py` (split out once this file hit the house cap). A barrier
on the thief's true cell is an instant capture (rule 46, ground-truth);
placing one also makes rule 47 (imprisonment) reachable here for the first
time — `step()`'s capture check is `run_local_subgame`'s own three-way check.

**PRD 14 sub-layer A**: the policy observes a belief estimate, never true
`thief_pos` — `_belief` (`belief_tracker.BeliefTracker`) advances every
step exactly like `orchestrator_turn.py::take_turn` does; `_encode()` feeds
its estimate (plus confidence) to the state encoder. Physics — capture,
terminal reward — stays ground-truth throughout; only what the policy
*observes* is uncertain. Deliberately-not-simulated channels, and why:
`belief_tracker.py`'s own docstring.

**PRD 14 post-gate follow-up**: a barrier restricting the *believed*
target's escape routes earns a small reward bonus (`reward.py`'s own
docstring covers why this term is a heuristic, not provably-safe like the
distance term) — built only after `barrier_restriction_metric.py` measured
this was genuinely rare (14.8%) in the trained policy's own choices.
"""

from __future__ import annotations

import random

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.domain.scoring import Outcome
from cop.reasoning.rl_state_encoding import State, encode_state
from cop.shared.config import GameConfig

from .belief_tracker import BeliefTracker
from .config import RLTrainingConfig
from .env_actions import legal_cop_actions
from .env_step import resolve_step
from .opponent_policies import ThiefMover


class SelfPlayEnv:
    """One training episode's worth of pursuit — movement and, since PRD 14
    sub-layer B, barrier placement."""

    def __init__(
        self,
        board: Board,
        game_config: GameConfig,
        rl_config: RLTrainingConfig,
        opponent: ThiefMover,
        belief_rng: random.Random,
    ) -> None:
        """`belief_rng` drives the synthetic thief-hint lie/truth coin flip
        (`BeliefTracker.fold_synthetic_hint`) — required, not defaulted, so
        every caller makes an explicit, considered choice about it. Must be
        a single stream reused across every episode of one training run,
        never reconstructed per episode: see `belief_tracker.py`'s own
        docstring for why a fresh stream each episode would teach a
        spurious step-index-correlated artifact instead of a real skill."""
        self._board = board
        self._game_config = game_config
        self._rl_config = rl_config
        self._opponent = opponent
        self._barriers = BarrierSet(quota=game_config.barrier_quota)  # PRD 14 sub-layer B: real quota
        self.cop_pos = Position(*game_config.cop_start)
        self.thief_pos = Position(*game_config.thief_start)
        self.steps_taken = 0
        self._belief = BeliefTracker(board, game_config, self._barriers, belief_rng)

    def reset(self) -> State:
        self.cop_pos = Position(*self._game_config.cop_start)
        self.thief_pos = Position(*self._game_config.thief_start)
        self.steps_taken = 0
        # Cleared in place, not reassigned — `_belief` holds a reference to
        # this exact object; a fresh BarrierSet here would silently desync it.
        self._barriers.placed.clear()
        self._belief.reset()
        return self._encode()

    def legal_actions(self) -> list[str]:
        return legal_cop_actions(self.cop_pos, self._board, self._barriers)

    def step(self, action: str) -> tuple[State, float, bool, Outcome | None]:
        """One cop action, capture check, and (if the game continues) one
        thief move for the next round — see `env_step.resolve_step`'s own
        docstring for the exact order and reasoning; extracted there once
        this file hit the house cap for a second time."""
        return resolve_step(self, action)

    def _encode(self) -> State:
        believed_pos, entropy, second_mode = self._belief.believed_targets()
        return encode_state(
            self.cop_pos, believed_pos, self._board, self._barriers,
            belief_entropy=entropy, second_mode_pos=second_mode,
        )
