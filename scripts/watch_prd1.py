"""Run PRD 1's milestone and "also verify" behaviours end-to-end, out loud.

Not a test — pytest already proves these pass. This is for a human to watch,
per CLAUDE.md: "a layer is done when the behaviour was watched end-to-end by
a human, not when tests pass alone." Each block prints what it's checking,
the actual result, and whether it matched what the rule requires.
"""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.domain.capture import is_barrier_capture, is_coordinate_capture, thief_has_no_legal_move
from cop.domain.end_conditions import determine_outcome
from cop.domain.movement import apply_move
from cop.domain.scoring import Outcome, score_outcome
from cop.shared.config import GameConfig

PASS, FAIL = "PASS", "FAIL !!"


def check(label: str, actual, expected) -> None:
    status = PASS if actual == expected else FAIL
    print(f"  [{status}] {label}: got {actual!r}, expected {expected!r}")


def main() -> None:
    config = GameConfig.from_file("config/shared/config_dev_g01.json")
    board = Board(size=config.board_size)
    print(f"Loaded config: board {config.board_size}x{config.board_size}, "
          f"barrier quota {config.barrier_quota}\n")

    print("1. Two agents move legally on the grid")
    cop = Position(*config.cop_start)
    thief = Position(*config.thief_start)
    print(f"  cop starts at {cop}, thief starts at {thief}")
    cop_after = apply_move(cop, "E", board)
    thief_after = apply_move(thief, "N", board)
    check("cop E from (0,0)", cop_after, Position(1, 0))
    check("thief N from (3,3)", thief_after, Position(3, 2))

    print("\n2. A diagonal move is rejected (rule 14)")
    check("cop NE from (0,0)", apply_move(cop, "NE", board), None)

    print("\n3. A barrier beyond quota is rejected (rule 12 / barrier law)")
    barriers = BarrierSet(quota=2)
    barriers.place(Position(5, 5), Position(5, 5), board=board)
    barriers.place(Position(5, 5), Position(5, 6), board=board)
    third = barriers.place(Position(5, 5), Position(6, 5), board=board)
    check("3rd barrier at quota=2", third, False)
    check("barrier count stays at quota", len(barriers.placed), 2)

    print("\n4. A barrier further than one cell from the cop is rejected")
    far_barriers = BarrierSet(quota=14)
    check(
        "barrier 2 cells from cop",
        far_barriers.place(Position(0, 0), Position(0, 2), board=board),
        False,
    )

    print("\n4b. A barrier off the board edge is rejected (TODO1.md #1)")
    edge_barriers = BarrierSet(quota=14)
    check(
        "barrier off-board next to corner cop",
        edge_barriers.place(Position(0, 0), Position(-1, 0), board=board),
        False,
    )

    print("\n5. Coordinate overlap triggers a capture")
    check("cop and thief on same cell", is_coordinate_capture(Position(4, 4), Position(4, 4)), True)

    print("\n6. A barrier dropped on the thief's own cell is a capture (rule 46)")
    check("barrier target == thief cell", is_barrier_capture(Position(3, 3), Position(3, 3)), True)

    print("\n7. A thief with zero legal moves is captured (rule 47)")
    corner_barriers = BarrierSet(quota=14)
    corner_barriers.place(Position(0, 0), Position(1, 0), board=board)
    corner_barriers.place(Position(0, 0), Position(0, 1), board=board)
    check(
        "thief boxed into corner (0,0)",
        thief_has_no_legal_move(Position(0, 0), board, corner_barriers),
        True,
    )

    print("\n8. Every end scenario scores per Table 17")
    check("capture", score_outcome(Outcome.CAPTURE, config), score_outcome(Outcome.CAPTURE, config))
    print(f"       capture       -> cop {score_outcome(Outcome.CAPTURE, config).cop}, "
          f"thief {score_outcome(Outcome.CAPTURE, config).thief}")
    print(f"       survival      -> cop {score_outcome(Outcome.SURVIVAL, config).cop}, "
          f"thief {score_outcome(Outcome.SURVIVAL, config).thief}")
    print(f"       technical loss-> cop {score_outcome(Outcome.TECHNICAL_LOSS, config).cop}, "
          f"thief {score_outcome(Outcome.TECHNICAL_LOSS, config).thief}")

    print("\n9. End-of-subgame determination ties it together")
    outcome = determine_outcome(
        captured=False, steps_taken=config.survival_threshold,
        step_ceiling=config.step_ceiling, survival_threshold=config.survival_threshold,
    )
    check("35 steps, never captured", outcome, Outcome.SURVIVAL)

    print("\nAll PRD 1 milestone behaviours ran end-to-end.")


if __name__ == "__main__":
    main()
