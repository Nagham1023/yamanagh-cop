"""Watch a diagonal move get rejected — and a legal move from the same cell
succeed right after it, so the rejection is visibly about the diagonal
specifically, not about the starting cell or something else going wrong.

Run:
    uv run python scripts/watch_diagonal_move.py
"""

from __future__ import annotations

from cop.domain.board import Board, Position
from cop.domain.movement import apply_move

BOARD = Board(size=7)


def main() -> None:
    start = Position(3, 3)
    print(f"Starting at {start} on a {BOARD.size}x{BOARD.size} board.\n")

    print("Diagonals (rule 14) — every one of these must come back None:")
    for direction in ["NE", "NW", "SE", "SW"]:
        result = apply_move(start, direction, BOARD)
        print(f"  move {direction!r:>5} -> {result!r}  (rejected)")

    print("\nThe fixed movement set (rule 13) — these all succeed from the same cell:")
    for direction in ["N", "E", "S", "W", "STAY"]:
        result = apply_move(start, direction, BOARD)
        print(f"  move {direction!r:>5} -> {result!r}  (accepted)")


if __name__ == "__main__":
    main()
