"""Integration tests: scenarios that chain multiple domain modules together,
the way a real turn loop will once PRD 2's orchestrator exists. Unit tests
already cover each module in isolation (movement, capture, scoring,
end_conditions separately) — this proves the modules agree with each other
when driven together, backing scripts/watch_capture_ends_game.py.
"""

from __future__ import annotations

from cop.domain.board import Board, Position
from cop.domain.capture import is_coordinate_capture
from cop.domain.end_conditions import determine_outcome
from cop.domain.movement import apply_move
from cop.domain.scoring import Outcome, Score, score_outcome


def test_cop_landing_on_thief_cell_ends_the_game(config):
    board = Board(size=config.board_size)
    cop = Position(*config.cop_start)
    thief = Position(*config.thief_start)  # stays put — this test is about capture, not evasion

    path_to_thief = ["E", "E", "E", "S", "S", "S"]
    outcome = None

    for steps_taken, direction in enumerate(path_to_thief, start=1):
        cop = apply_move(cop, direction, board)
        assert cop is not None, "scripted path must stay on the board"

        captured = is_coordinate_capture(cop, thief)
        outcome = determine_outcome(
            captured=captured,
            steps_taken=steps_taken,
            step_ceiling=config.step_ceiling,
            survival_threshold=config.survival_threshold,
        )
        if outcome is not None:
            break

    assert cop == thief
    assert outcome is Outcome.CAPTURE
    assert score_outcome(outcome, config) == Score(cop=20, thief=5)
