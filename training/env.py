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
from .env_actions import apply_cop_action, barrier_restricts_believed_target, legal_cop_actions
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
        # Cleared in place, not reassigned — `_belief` holds a reference to
        # this exact object; a fresh BarrierSet here would silently desync it.
        self._barriers.placed.clear()
        self._belief.reset()
        return self._encode()

    def legal_actions(self) -> list[str]:
        return legal_cop_actions(self.cop_pos, self._board, self._barriers)

    def step(self, action: str) -> tuple[State, float, bool, Outcome | None]:
        """One cop action, then a capture check (coordinate, barrier/rule-46,
        imprisonment/rule-47 — `run_local_subgame`'s own three-way check,
        exact order), then, only if the game continues, one thief move for
        the *next* round — the thief walking onto the cop is never itself a
        capture. Returns `(next_state, reward, done, outcome)`.

        `believed_target_pos` is read before this action mutates anything
        and before `self._belief.advance(...)` runs below — the belief the
        policy actually conditioned its choice on, for
        `env_actions.barrier_restricts_believed_target`."""
        prev_distance = _manhattan(self.cop_pos, self.thief_pos)
        believed_target_pos, _confidence = self._belief.believed_target()
        cop_pos_before_action = self.cop_pos
        self.cop_pos, barrier_capture = apply_cop_action(
            action, self.cop_pos, self.thief_pos, self._board, self._barriers
        )
        self.steps_taken += 1

        restricts_believed_target = barrier_restricts_believed_target(
            action, cop_pos_before_action, believed_target_pos, self._barriers
        )

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
            # Thief moves only when the round didn't already end on the cop's own action.
            thief_direction = self._opponent(self.thief_pos, self._board, self._barriers)
            self.thief_pos = apply_move(self.thief_pos, thief_direction, self._board) or self.thief_pos

        new_distance = _manhattan(self.cop_pos, self.thief_pos)
        reward = step_reward(
            prev_distance=prev_distance,
            new_distance=new_distance,
            outcome=outcome,
            game_config=self._game_config,
            rl_config=self._rl_config,
            restricts_believed_target=restricts_believed_target,
        )
        return self._encode(), reward, outcome is not None, outcome

    def _encode(self) -> State:
        believed_pos, confidence = self._belief.believed_target()
        return encode_state(
            self.cop_pos, believed_pos, self._board, self._barriers, belief_confidence=confidence
        )
