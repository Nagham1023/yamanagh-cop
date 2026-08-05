"""Watch a short normal game: both agents move one legal step per turn.

Nothing here is a rule check — it's plain movement, printed turn by turn, so
you can see positions change by exactly one cell at a time, the way rules
13/14 require (one orthogonal step, or stay — never more, never diagonal).

Run:
    uv run python scripts/watch_normal_game.py
"""

from __future__ import annotations

from cop.domain.board import Board, Position
from cop.domain.movement import apply_move
from cop.shared.config import GameConfig

COP_MOVES = ["E", "E", "S", "S", "W", "N"]
# Deliberately kept clear of the cop's path — this script is only about
# movement, not capture (see watch_capture_ends_game.py for that).
THIEF_MOVES = ["S", "E", "S", "E", "N", "N"]


def main() -> None:
    config = GameConfig.from_file("config/shared/config_dev_g01.json")
    board = Board(size=config.board_size)
    cop = Position(*config.cop_start)
    thief = Position(*config.thief_start)

    print(f"Board {board.size}x{board.size}. cop starts at {cop}, thief starts at {thief}\n")

    for turn, (cop_dir, thief_dir) in enumerate(zip(COP_MOVES, THIEF_MOVES, strict=True), start=1):
        print(f"Turn {turn}:")

        new_cop = apply_move(cop, cop_dir, board)
        print(f"  cop   {cop_dir:>4}: {cop} -> {new_cop}")
        cop = new_cop or cop

        new_thief = apply_move(thief, thief_dir, board)
        print(f"  thief {thief_dir:>4}: {thief} -> {new_thief}")
        thief = new_thief or thief

    print(f"\nFinal positions: cop {cop}, thief {thief}")


if __name__ == "__main__":
    main()
