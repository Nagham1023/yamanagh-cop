"""Watch PRD 4's milestone run live: two sections, matching the split
between the language/deception algorithm (local, no network) and wiring
correctness (one real round-trip) — see PRD-4-language-and-scent.md,
Design Questions 3/4.

Reuses tests/integration/_helpers.py to launch the second peer for section
2, same helper the automated integration tests use.

Run:
    uv run python scripts/watch_prd4_language.py
"""

from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tests" / "integration"))

from _helpers import REPO_CONFIG, free_port, spawn_server, wait_for_port  # noqa: E402

from cop.domain.board import Board, Position  # noqa: E402
from cop.memory.belief import BeliefMap  # noqa: E402
from cop.memory.scent import ScentField  # noqa: E402
from cop.orchestrator import Orchestrator  # noqa: E402
from cop.reasoning.cop_brain import CopBrain  # noqa: E402
from cop.reasoning.hint import decide_intent, generate_hint, interpret_hint  # noqa: E402
from cop.shared.config import GameConfig  # noqa: E402
from cop.tools.hint_providers import TemplateHintProvider  # noqa: E402


def section_1_local_language(config: GameConfig, board: Board) -> None:
    print("1. Local language + deception — no Orchestrator, no network (the milestone)")
    true_pos = Position(0, 0)
    provider = TemplateHintProvider()
    rng = random.Random(20260806)

    for label, lie_probability in (("truthful", 0.0), ("lying", 1.0)):
        intent = decide_intent(lie_probability, rng)
        hint_text = generate_hint(true_pos, provider, config, intent)
        focal_point = interpret_hint(hint_text, board)
        belief = BeliefMap.uniform(board)
        before = belief.probability(focal_point)
        belief.update_from_hint(focal_point, board)
        after = belief.probability(focal_point)
        print(
            f"  {label:9s} intent={intent!s:5s} hint={hint_text!r:45s} "
            f"-> belief interpreted focal point {focal_point}, "
            f"probability there {before:.4f} -> {after:.4f}"
        )

    print("\n  scent decay at the cop's true position over 5 steps (independent of the hint above):")
    scent = ScentField.from_config(config)
    scent.emit(true_pos)
    for step in range(5):
        level = scent.sample(true_pos, board)[true_pos]
        print(f"    step {step}: {level:.4f}")
        scent.decay()


def section_2_one_real_round_trip(config: GameConfig) -> None:
    print("\n2. One real round-trip — proving take_turn() sends language, not coordinates")
    port = free_port()
    log_path = Path("/tmp/watch_prd4_trace.jsonl")
    log_path.unlink(missing_ok=True)
    peer = spawn_server(port, log_path)

    try:
        wait_for_port(port)
        print(f"  peer is a separate OS process, pid={peer.pid}, listening on port {port}")

        client_log = Path("/tmp/watch_prd4_client_trace.jsonl")
        client_log.unlink(missing_ok=True)
        client = Orchestrator(config, CopBrain(), log_path=str(client_log))
        print(f"  before: state={client.state_machine.state}, own_pos={client.game_state.own_pos}")

        result = asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

        events = [
            line
            for line in client_log.read_text(encoding="utf-8").splitlines()
            if '"sending_hint"' in line
        ]
        print(f"  after:  state={client.state_machine.state}, own_pos={client.game_state.own_pos}")
        print(f"  peer received and acked: {result}")
        print(f"  actual text that crossed the wire: {events[0]}")
    finally:
        peer.terminate()
        peer.wait(timeout=5)


def main() -> None:
    config = GameConfig.from_file(REPO_CONFIG)
    board = Board(size=config.board_size)
    section_1_local_language(config, board)
    section_2_one_real_round_trip(config)
    print("\nAll PRD 4 milestone behaviours ran end-to-end.")


if __name__ == "__main__":
    main()
