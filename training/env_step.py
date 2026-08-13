"""`SelfPlayEnv.step()`'s own body — split out of `env.py` once that file hit
the 150-line house cap for the second time (the first split produced
`env_actions.py`; this one extracts the per-step orchestration itself,
leaving `SelfPlayEnv.step()` a one-line delegator).

`resolve_step` takes the env instance directly, not individual fields —
unlike `env_actions.py`'s free functions (which only ever needed a handful
of positional values), this step touches most of `SelfPlayEnv`'s own state
at once, and passing the object keeps that visible rather than smearing it
across a dozen parameters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cop.domain.board import Position
from cop.domain.capture import is_coordinate_capture, thief_has_no_legal_move
from cop.domain.end_conditions import determine_outcome
from cop.domain.movement import apply_move
from cop.domain.scoring import Outcome
from cop.reasoning.rl_state_encoding import State

from .env_actions import (
    apply_cop_action,
    barrier_restricts_believed_target,
    barrier_restricts_chokepoint,
)
from .reward import step_reward

if TYPE_CHECKING:
    from .env import SelfPlayEnv


def _manhattan(a: Position, b: Position) -> int:
    return abs(a.col - b.col) + abs(a.row - b.row)


def resolve_step(env: SelfPlayEnv, action: str) -> tuple[State, float, bool, Outcome | None]:
    """One cop action, then a capture check (coordinate, barrier/rule-46,
    imprisonment/rule-47 — `run_local_subgame`'s own three-way check, exact
    order), then, only if the game continues, one thief move for the *next*
    round — the thief walking onto the cop is never itself a capture.
    Returns `(next_state, reward, done, outcome)`.

    `believed_target_pos`/`prev_expected_distance` are read before this
    action mutates anything and before `env._belief.advance(...)` runs
    below — the belief the policy actually conditioned its choice on, for
    `env_actions.barrier_restricts_believed_target`/`barrier_restricts_chokepoint`
    and the belief-weighted shaping term in `reward.py`. `new_expected_distance`
    is read at the very end, after belief has been folded — bracketing it
    the same way `prev_distance`/`new_distance` already bracket ground truth."""
    prev_distance = _manhattan(env.cop_pos, env.thief_pos)
    prev_expected_distance = env._belief.belief_map.expected_manhattan_distance(env.cop_pos)
    believed_target_pos, _entropy, second_mode = env._belief.believed_targets()
    cop_pos_before_action = env.cop_pos
    env.cop_pos, barrier_capture = apply_cop_action(
        action, env.cop_pos, env.thief_pos, env._board, env._barriers
    )
    env.steps_taken += 1

    restricts_believed_target = barrier_restricts_believed_target(
        action, cop_pos_before_action, believed_target_pos, env._barriers
    ) or barrier_restricts_chokepoint(
        action, cop_pos_before_action, believed_target_pos, second_mode, env._barriers
    )

    captured = (
        barrier_capture
        or is_coordinate_capture(env.cop_pos, env.thief_pos)
        or thief_has_no_legal_move(env.thief_pos, env._board, env._barriers)
    )

    outcome = determine_outcome(
        captured=captured,
        steps_taken=env.steps_taken,
        step_ceiling=env._game_config.step_ceiling,
        survival_threshold=env._game_config.survival_threshold,
    )
    if outcome is None:
        # Belief update happens only when the episode continues: on a
        # terminal step, train_loop.py's own Bellman update never reads
        # next_state's Q-value at all (`best_next = 0.0 if done`), so
        # there is nothing for an un-updated final belief to affect.
        env._belief.advance(env.cop_pos)
        # Thief moves only when the round didn't already end on the cop's own action.
        thief_direction = env._opponent(env.thief_pos, env._board, env._barriers)
        env.thief_pos = apply_move(env.thief_pos, thief_direction, env._board) or env.thief_pos
        # Simulates receiving the thief's own real scent map, reflecting its
        # post-move position — mirrors orchestrator_turn.take_turn's real
        # ordering (a peer's scent reflects wherever it just moved to)
        # closely enough to be functionally equivalent, since nothing else
        # touches belief between here and the next _encode() call. Order
        # relative to the hint fold below is inert (both are multiply-then-
        # renormalize updates); scent first, hint second, for readability.
        env._belief.fold_peer_scent(env.thief_pos)
        env._belief.fold_synthetic_hint(
            env.thief_pos, env._rl_config.synthetic_thief_lie_probability
        )

    new_distance = _manhattan(env.cop_pos, env.thief_pos)
    new_expected_distance = env._belief.belief_map.expected_manhattan_distance(env.cop_pos)
    reward = step_reward(
        prev_distance=prev_distance,
        new_distance=new_distance,
        outcome=outcome,
        game_config=env._game_config,
        rl_config=env._rl_config,
        restricts_believed_target=restricts_believed_target,
        prev_expected_distance=prev_expected_distance,
        new_expected_distance=new_expected_distance,
    )
    return env._encode(), reward, outcome is not None, outcome
