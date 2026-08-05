"""Watch the cop place barriers up to the config-driven quota, and watch the
next one get refused.

Every placement prints a declaration with the exact cell used. The declared
cell and the cell actually stored in `BarrierSet.placed` are the same Python
value — there is no separate "what we said" versus "what we did," so
truthfulness here is structural, not just promised. Real cross-process
declaration (rules 15/16, to an actual opponent) arrives with PRD 2's
networking layer; this is the single-process version of the same idea.

Run:
    uv run python scripts/watch_barrier_placements.py
"""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.shared.config import GameConfig


def declare(cell: Position, count: int, quota: int) -> None:
    print(f"  [DECLARE] barrier placed at ({cell.col}, {cell.row}) — {count}/{quota}")


def snake_path(board: Board) -> list[Position]:
    """Every cell on the board, in a snake order — far more than any quota needs."""
    path: list[Position] = []
    for row in range(board.size):
        cols = range(board.size) if row % 2 == 0 else range(board.size - 1, -1, -1)
        path.extend(Position(col, row) for col in cols)
    return path


def main() -> None:
    config = GameConfig.from_file("config/shared/config_dev_g01.json")
    board = Board(size=config.board_size)
    barriers = BarrierSet(quota=config.barrier_quota)
    print(f"Quota, read from config/shared/config_dev_g01.json: {config.barrier_quota}\n")

    path = snake_path(board)

    for cell in path[: config.barrier_quota]:
        # Barrier placed on the cell the cop currently occupies (manhattan
        # distance 0) — always legal, and walking a fresh cell each time
        # keeps every placement distinct.
        placed = barriers.place(cop_pos=cell, target=cell, board=board)
        assert placed, f"expected {cell} to be a legal placement"
        declare(cell, len(barriers.placed), config.barrier_quota)

    print(f"\n{len(barriers.placed)} of {config.barrier_quota} barriers placed. Quota reached.")

    fifteenth = path[config.barrier_quota]
    print(f"\nAttempting one more, at {fifteenth} (a fresh, otherwise-legal cell)...")
    accepted = barriers.place(cop_pos=fifteenth, target=fifteenth, board=board)
    print(f"  accepted: {accepted}  <- refused: quota exhausted, not because the cell is illegal")
    print(f"  barriers still on the board: {len(barriers.placed)} (unchanged)")


if __name__ == "__main__":
    main()
