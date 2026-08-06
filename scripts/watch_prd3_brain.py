"""Watch PRD 3's milestone run live: two sections, matching the split
between algorithm correctness (local, no network) and wiring correctness
(one real round-trip) — see PRD-3-blind-strategy.md, Design Question 3.

Reuses tests/integration/_helpers.py to launch the second peer for section
2, same helper the automated integration tests use.

Run:
    uv run python scripts/watch_prd3_brain.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tests" / "integration"))
sys.path.insert(0, str(REPO_ROOT / "tests" / "support"))

from _helpers import REPO_CONFIG, free_port, spawn_server, wait_for_port  # noqa: E402
from greedy_thief_mover import greedy_thief_move  # noqa: E402

from cop.domain.board import Board  # noqa: E402
from cop.orchestrator import Orchestrator  # noqa: E402
from cop.reasoning.brain_base import Move  # noqa: E402
from cop.reasoning.cop_brain import CopBrain  # noqa: E402
from cop.reasoning.subgame import run_local_subgame  # noqa: E402
from cop.shared.config import GameConfig  # noqa: E402


def _narrate(round_number, action, cop_pos, thief_pos, barriers) -> None:
    kind = f"moves {action.direction}" if isinstance(action, Move) else f"places barrier {action.target}"
    distance = abs(cop_pos.col - thief_pos.col) + abs(cop_pos.row - thief_pos.row)
    print(
        f"  round {round_number}: cop {kind} -> {cop_pos}, thief at {thief_pos}, "
        f"distance {distance}, barriers placed {len(barriers)}"
    )


def _stay(own_pos, board, barriers) -> str:
    return "STAY"


def section_1_local_pursuit(config: GameConfig) -> None:
    print("1. Local pursuit — no Orchestrator, no network (the milestone)")
    board = Board(size=config.board_size)

    print("  a) static known target:")
    outcome = run_local_subgame(CopBrain(), _stay, board, config, on_turn=_narrate)
    print(f"  outcome: {outcome.value}")

    print("\n  b) moving target — the greedy escape-route-preferring thief fixture:")
    outcome = run_local_subgame(CopBrain(), greedy_thief_move, board, config, on_turn=_narrate)
    print(f"  outcome: {outcome.value}")


def section_2_one_real_round_trip(config: GameConfig) -> None:
    print("\n2. One real round-trip — proving Orchestrator.take_turn() is wired (not the algorithm)")
    port = free_port()
    log_path = Path("/tmp/watch_prd3_trace.jsonl")
    log_path.unlink(missing_ok=True)
    peer = spawn_server(port, log_path)

    try:
        wait_for_port(port)
        print(f"  peer is a separate OS process, pid={peer.pid}, listening on port {port}")

        client = Orchestrator(config, CopBrain(), log_path=str(Path("/tmp/watch_prd3_client_trace.jsonl")))
        print(f"  before: state={client.state_machine.state}, own_pos={client.game_state.own_pos}")

        result = asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

        print(f"  after:  state={client.state_machine.state}, own_pos={client.game_state.own_pos}")
        print(f"  peer received and acked: {result}")
    finally:
        peer.terminate()
        peer.wait(timeout=5)


def main() -> None:
    config = GameConfig.from_file(REPO_CONFIG)
    section_1_local_pursuit(config)
    section_2_one_real_round_trip(config)
    print("\nAll PRD 3 milestone behaviours ran end-to-end.")


if __name__ == "__main__":
    main()
