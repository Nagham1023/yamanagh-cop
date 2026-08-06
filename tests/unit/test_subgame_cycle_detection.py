"""Cycle detection (requested review addition): step_ceiling can mask an
oscillating cop as a legitimate SURVIVAL outcome — a cop stuck bouncing
between two cells runs out the clock and determine_outcome correctly
returns SURVIVAL, so a bare outcome assertion can't tell "genuinely
survived" from "was broken the whole time."

Both the cop brain and the thief mover here are deterministic pure
functions of (position, board, barriers) — so if the full triple
`(cop_pos, thief_pos, frozenset(barriers))` ever repeats, every subsequent
step is forced to repeat too, meaning the game can never reach capture from
that point on. A repeat is therefore a cycle by definition, not a
heuristic — this is what makes "assert no repeated triple" a sound proxy
for "the pursuit made genuine progress toward the capture it achieved."
"""

from __future__ import annotations

from greedy_thief_mover import greedy_thief_move

from cop.domain.board import Board
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.subgame import run_local_subgame


def _stay(own_pos, board, barriers) -> str:
    return "STAY"


def _assert_no_repeats(config, thief_mover) -> None:
    board = Board(size=config.board_size)
    seen = set()

    def _record(round_number, action, cop_pos, thief_pos, barriers) -> None:
        key = (cop_pos, thief_pos, barriers)
        assert key not in seen, (
            f"state repeated at round {round_number}: {key} — "
            f"the cop is cycling, not converging"
        )
        seen.add(key)

    outcome = run_local_subgame(CopBrain(), thief_mover, board, config, on_turn=_record)

    assert outcome.value == "capture"


def test_no_state_repeats_on_the_way_to_capturing_a_static_target(config):
    _assert_no_repeats(config, _stay)


def test_no_state_repeats_on_the_way_to_capturing_the_moving_greedy_thief(config):
    _assert_no_repeats(config, greedy_thief_move)
