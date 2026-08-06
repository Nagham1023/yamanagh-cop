"""Reproducibility: the whole game trace, not just each decision in
isolation, must be reconstructible from the same starting state. Matters
directly at PRD 7 — the replay verifier depends on a recorded game being
reproducible from its inputs.
"""

from __future__ import annotations

from greedy_thief_mover import greedy_thief_move

from cop.domain.board import Board
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.subgame import run_local_subgame


def _record_actions(config, thief_mover) -> tuple[list, object]:
    board = Board(size=config.board_size)
    actions = []

    def _record(round_number, action, cop_pos, thief_pos, barriers) -> None:
        actions.append(action)

    outcome = run_local_subgame(CopBrain(), thief_mover, board, config, on_turn=_record)
    return actions, outcome


def test_the_same_subgame_run_twice_produces_an_identical_action_sequence_static_target(config):
    actions_1, outcome_1 = _record_actions(config, lambda own_pos, board, barriers: "STAY")
    actions_2, outcome_2 = _record_actions(config, lambda own_pos, board, barriers: "STAY")

    assert actions_1 == actions_2
    assert outcome_1 == outcome_2


def test_the_same_subgame_run_twice_produces_an_identical_action_sequence_moving_thief(config):
    actions_1, outcome_1 = _record_actions(config, greedy_thief_move)
    actions_2, outcome_2 = _record_actions(config, greedy_thief_move)

    assert actions_1 == actions_2
    assert outcome_1 == outcome_2
