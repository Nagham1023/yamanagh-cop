"""Offline measurement: does a trained Q-table's own barrier-placement
choices already tend to restrict the *believed* target's escape routes
(PRD 14 post-gate follow-up)?

The proposal that motivated this file was to add a new reward-shaping term
explicitly rewarding "chokepoint blocking toward the believed target." That
term would NOT be provably policy-invariant the way `reward.py`'s existing
potential-based distance shaping is (Ng/Harada/Russell's guarantee only
covers that exact shape) — so building it should be conditional on a real,
measured gap, not on the idea sounding reasonable. This module answers that
question against a real trained checkpoint before any such term is written.

`State`'s own `(dx, dy)` *is* the target's position relative to the cop —
no live `Board`/`Position` needed to check whether a `BARRIER_<dir>`
candidate (offset `DELTAS[direction]` from the cop, same origin) lands
within Manhattan distance 1 of it. This is `CopBrain._restricts_target`'s
own check, re-expressed in the Q-table's relative-coordinate space —
deliberately duplicated rather than imported: production code under
`src/cop/` cannot depend on `training/` importing it back (the direction
`test_training_boundary.py` enforces), and this offline-analysis module has
no live `Position` to hand `CopBrain`'s own version anyway. Same
"duplicated, not imported" precedent `greedy_escape_thief`/
`tests/support/greedy_thief_mover.py` and `rl_state_encoding.py`'s own
`_count_open_neighbours` already set for this exact kind of small,
load-bearing repetition.

`dx`/`dy` are clamped to `_CLAMP_RADIUS` at encoding time (see
`rl_state_encoding.py`) — this measures whether the policy's choice
restricts its own *perceived* (possibly-saturated) target position, which
is the semantically correct thing to measure here: the policy itself never
had access to anything beyond the clamped signal either.
"""

from __future__ import annotations

from cop.domain.movement import DELTAS
from cop.reasoning.rl_state_encoding import State


def barrier_restricts_relative_target(direction: str, dx: int, dy: int) -> bool:
    """True iff `BARRIER_<direction>`'s candidate cell is within Manhattan
    distance 1 of the target's own relative position `(dx, dy)` — landing
    exactly on the target's cell (distance 0) does not count, faithfully
    matching `CopBrain._restricts_target`'s own `== 1`, not `<= 1`."""
    delta = DELTAS[direction]
    return abs(delta.col - dx) + abs(delta.row - dy) == 1


def measure_barrier_restriction_rate(q_values: dict[State, dict[str, float]]) -> dict:
    """Over every state whose Q-table-ranked-best action is a barrier
    placement, the fraction that restrict the believed target's escape
    routes. `fraction_restricting` is `None` (not `0.0`) when no state ever
    top-ranks a barrier at all — a genuinely different finding ("RL rarely
    chooses to place a barrier" vs. "it does, but never usefully") that
    must not be conflated."""
    restricting = 0
    non_restricting = 0
    for state, row in q_values.items():
        dx, dy, *_rest = state
        best = max(row, key=row.__getitem__)  # matches RLQTable.ranked_actions' own tie-break
        if not best.startswith("BARRIER_"):
            continue
        direction = best.removeprefix("BARRIER_")
        if barrier_restricts_relative_target(direction, dx, dy):
            restricting += 1
        else:
            non_restricting += 1
    total = restricting + non_restricting
    return {
        "barrier_top_states": total,
        "restricting": restricting,
        "fraction_restricting": restricting / total if total else None,
    }
