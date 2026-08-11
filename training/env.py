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

Barrier placement is never simulated here (PRD 11's own "Explicitly out of
scope": barrier-placement RL is a separate problem). `RLCopBrain` only ever
learns `_pick_move`; `_decide_move`'s barrier heuristic stays the inherited
`CopBrain` one, applied only at real/`run_local_subgame` time, never here.
"""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.domain.capture import is_coordinate_capture
from cop.domain.end_conditions import determine_outcome
from cop.domain.movement import apply_move
from cop.domain.scoring import Outcome
from cop.reasoning.rl_state_encoding import State, encode_state
from cop.shared.config import GameConfig

from .config import RLTrainingConfig
from .opponent_policies import ThiefMover
from .reward import step_reward

_LEGAL_MOVE_ACTIONS = ("N", "E", "S", "W", "STAY")


def _manhattan(a: Position, b: Position) -> int:
    return abs(a.col - b.col) + abs(a.row - b.row)


class SelfPlayEnv:
    """One training episode's worth of pursuit, movement-only, no barriers."""

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
        self._barriers = BarrierSet(quota=0)  # never placed into; movement-only training
        self.cop_pos = Position(*game_config.cop_start)
        self.thief_pos = Position(*game_config.thief_start)
        self.steps_taken = 0

    def reset(self) -> State:
        self.cop_pos = Position(*self._game_config.cop_start)
        self.thief_pos = Position(*self._game_config.thief_start)
        self.steps_taken = 0
        return self._encode()

    def legal_actions(self) -> list[str]:
        legal = ["STAY"]
        for direction in _LEGAL_MOVE_ACTIONS:
            if direction == "STAY":
                continue
            if apply_move(self.cop_pos, direction, self._board) is not None:
                legal.append(direction)
        return legal

    def step(self, action: str) -> tuple[State, float, bool, Outcome | None]:
        """One cop move, capture check, then — only if the game continues —
        one thief move for the *next* round. Capture is checked exactly
        once, immediately after the cop's own move, matching
        `run_local_subgame`'s exact order: the thief walking onto the cop's
        cell is never itself a capture (only the cop landing on the thief,
        or a barrier on the thief's cell, count — `domain/capture.py`), so
        checking again after the thief moves would be physics-wrong, not
        just redundant. Returns `(next_state, reward, done, outcome)`."""
        prev_distance = _manhattan(self.cop_pos, self.thief_pos)
        destination = apply_move(self.cop_pos, action, self._board)
        self.cop_pos = destination if destination is not None else self.cop_pos
        self.steps_taken += 1

        captured = is_coordinate_capture(self.cop_pos, self.thief_pos)

        outcome = determine_outcome(
            captured=captured,
            steps_taken=self.steps_taken,
            step_ceiling=self._game_config.step_ceiling,
            survival_threshold=self._game_config.survival_threshold,
        )
        if outcome is None:
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
        return encode_state(self.cop_pos, self.thief_pos, self._board, self._barriers)
