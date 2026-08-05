"""Watch the cop walk onto the thief's cell and end the game by capture.

The thief holds still on purpose — this script is about what happens the
instant coordinates overlap, not about pursuit strategy (that's PRD 3).

Run:
    uv run python scripts/watch_capture_ends_game.py
"""

from __future__ import annotations

from cop.domain.board import Board, Position
from cop.domain.capture import is_coordinate_capture
from cop.domain.end_conditions import determine_outcome
from cop.domain.movement import apply_move
from cop.domain.scoring import score_outcome
from cop.shared.config import GameConfig

# A scripted path, not a strategy — just enough moves to land the cop
# exactly on the thief's starting cell.
COP_PATH = ["E", "E", "E", "S", "S", "S"]


def main() -> None:
    config = GameConfig.from_file("config/shared/config_dev_g01.json")
    board = Board(size=config.board_size)
    cop = Position(*config.cop_start)
    thief = Position(*config.thief_start)
    print(f"cop starts at {cop}, thief stays at {thief}\n")

    for steps_taken, direction in enumerate(COP_PATH, start=1):
        new_cop = apply_move(cop, direction, board)
        print(f"Turn {steps_taken}: cop {direction} -> {new_cop}")
        cop = new_cop or cop

        captured = is_coordinate_capture(cop, thief)
        outcome = determine_outcome(
            captured=captured,
            steps_taken=steps_taken,
            step_ceiling=config.step_ceiling,
            survival_threshold=config.survival_threshold,
        )
        if outcome is not None:
            score = score_outcome(outcome, config)
            print(f"\n  GAME OVER after {steps_taken} steps — {outcome.value}")
            print(f"  cop lands on {cop}, thief was at {thief} (captured={captured})")
            print(f"  score -> cop {score.cop}, thief {score.thief}")
            return

    print("\nGame did not end within the scripted path.")


if __name__ == "__main__":
    main()
