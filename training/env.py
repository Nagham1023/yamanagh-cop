"""SelfPlayEnv: step-based training environment over `domain/` primitives directly (PRD 11).

Deliberately not built on `reasoning/subgame.py::run_local_subgame` even
though that function already is a pure-Python local turn loop: training's
epsilon-greedy exploration must choose the *movement* action itself (with
exploration noise), not delegate it to an already-decided
`BrainBase._decide_move` call the way `run_local_subgame` does. Reusing it
would mean no way to inject the action being learned.

Instead this reimplements the same physics shape directly, and
`tests/unit/test_training_env_parity.py` proves the two are physics-
identical (same outcome, given the same fixed movement policy and the same
seeded thief mover) — a regression-tested fact, not an assumed one.

**PRD 14 sub-layer B**: barrier placement *is* now simulated (PRD 11's
original "explicitly out of scope" call, reversed deliberately). Four
`BARRIER_<dir>` actions — the cop's orthogonal neighbours only, matching
`CopBrain._barrier_candidates`' shape — filtered through the real
`BarrierSet.can_place`, resolved via `env_actions.apply_cop_action`
(split out once this file hit the house cap). A barrier on the thief's
true cell is an instant capture (rule 46, unconditional, ground-truth,
mirroring `run_local_subgame`); placing one also makes rule 47
(imprisonment) reachable here for the first time — `step()`'s capture
check is the same three-way check `run_local_subgame` already used.

**PRD 14 sub-layer A**: the policy no longer observes the true `thief_pos`
directly. `_belief` (`belief_tracker.BeliefTracker`) tracks the same two
objects a real turn updates, advanced every step exactly like
`orchestrator_turn.py::take_turn` does; `_encode()` feeds its belief
estimate (plus how confident it is) to the state encoder instead of
`thief_pos`. Physics — the capture check, the terminal reward — stays
ground-truth throughout; only what the *policy observes* is now uncertain.
Deliberately-not-simulated channels, and why: `belief_tracker.py`'s own
module docstring.
"""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.domain.capture import is_coordinate_capture, thief_has_no_legal_move
from cop.domain.end_conditions import determine_outcome
from cop.domain.movement import apply_move
from cop.domain.scoring import Outcome
from cop.reasoning.rl_state_encoding import State, encode_state
from cop.shared.config import GameConfig

from .belief_tracker import BeliefTracker
from .config import RLTrainingConfig
from .env_actions import apply_cop_action, legal_cop_actions
from .opponent_policies import ThiefMover
from .reward import step_reward


def _manhattan(a: Position, b: Position) -> int:
    return abs(a.col - b.col) + abs(a.row - b.row)


class SelfPlayEnv:
    """One training episode's worth of pursuit — movement and, since PRD 14
    sub-layer B, barrier placement."""

    def __init__(
        self,
        board: Board,
        game_config: GameConfig,
        rl_config: RLTrainingConfig,
        opponent: ThiefMover,
    ) -> None:
        self._board = board
        self._game_config = game_config
        self._rl_config = rl_config
        self._opponent = opponent
        self._barriers = BarrierSet(quota=game_config.barrier_quota)  # PRD 14 sub-layer B: real quota
        self.cop_pos = Position(*game_config.cop_start)
        self.thief_pos = Position(*game_config.thief_start)
        self.steps_taken = 0
        self._belief = BeliefTracker(board, game_config, self._barriers)

    def reset(self) -> State:
        self.cop_pos = Position(*self._game_config.cop_start)
        self.thief_pos = Position(*self._game_config.thief_start)
        self.steps_taken = 0
        # PRD 14 sub-layer B: barriers must not persist across episodes.
        # Cleared in place (not reassigned to a new BarrierSet) — `_belief`
        # holds a reference to this exact object; a fresh object here would
        # silently desync it.
        self._barriers.placed.clear()
        self._belief.reset()
        return self._encode()

    def legal_actions(self) -> list[str]:
        return legal_cop_actions(self.cop_pos, self._board, self._barriers)

    def step(self, action: str) -> tuple[State, float, bool, Outcome | None]:
        """One cop action (move, or a barrier placement that forgoes
        movement — `env_actions.apply_cop_action`), then a capture check,
        then, only if the game continues, one thief move for the *next*
        round. Capture is checked exactly once, immediately after the cop's
        own action, matching `run_local_subgame`'s exact order and its
        exact three-way check (coordinate, barrier/rule-46, imprisonment/
        rule-47 — the last two only reachable now that barriers are real).
        The thief walking onto the cop's cell is never itself a capture, so
        checking again after the thief moves would be physics-wrong, not
        just redundant. Returns `(next_state, reward, done, outcome)`."""
        prev_distance = _manhattan(self.cop_pos, self.thief_pos)
        self.cop_pos, barrier_capture = apply_cop_action(
            action, self.cop_pos, self.thief_pos, self._board, self._barriers
        )
        self.steps_taken += 1

        captured = (
            barrier_capture
            or is_coordinate_capture(self.cop_pos, self.thief_pos)
            or thief_has_no_legal_move(self.thief_pos, self._board, self._barriers)
        )

        outcome = determine_outcome(
            captured=captured,
            steps_taken=self.steps_taken,
            step_ceiling=self._game_config.step_ceiling,
            survival_threshold=self._game_config.survival_threshold,
        )
        if outcome is None:
            # Belief update happens only when the episode continues: on a
            # terminal step, train_loop.py's own Bellman update never reads
            # next_state's Q-value at all (`best_next = 0.0 if done`), so
            # there is nothing for an un-updated final belief to affect.
            self._belief.advance(self.cop_pos)
            # Thief moves only when the round didn't already end on the
            # cop's own action — same order run_local_subgame uses.
            thief_direction = self._opponent(self.thief_pos, self._board, self._barriers)
            self.thief_pos = apply_move(self.thief_pos, thief_direction, self._board) or self.thief_pos

        new_distance = _manhattan(self.cop_pos, self.thief_pos)
        reward = step_reward(
            prev_distance=prev_distance,
            new_distance=new_distance,
            outcome=outcome,
            game_config=self._game_config,
            rl_config=self._rl_config,
        )
        return self._encode(), reward, outcome is not None, outcome

    def _encode(self) -> State:
        believed_pos, confidence = self._belief.believed_target()
        return encode_state(
            self.cop_pos, believed_pos, self._board, self._barriers, belief_confidence=confidence
        )
