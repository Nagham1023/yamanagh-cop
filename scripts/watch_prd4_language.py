"""Watch PRD 4's milestone run live: two sections, matching the split
between the language/deception algorithm (local, no network) and wiring
correctness (one real round-trip) — see PRD-4-language-and-scent.md,
Design Questions 3/4, and Revision 3's Tool-based scent-map corroboration.

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

    print("\n  scent decay at the cop's true position over 5 steps (agent has since moved away):")
    scent = ScentField.from_config(config)
    scent.advance(true_pos, board)
    far_pos = Position(board.size - 1, board.size - 1)
    for step in range(5):
        level = scent.sample(true_pos, board)[true_pos]
        print(f"    step {step}: {level:.4f}")
        scent.advance(far_pos, board)

    print("\n  Revision 3 — the corroboration mechanic: a lying claim vs the peer's own real scent map")
    corroboration_true_pos = Position(1, 5)  # south-west
    previous_pos = Position(3, 4)  # nearby, an ordinary "just arrived here" trajectory —
    # deliberately NOT interpret_hint's own north-east decode cell (5, 1): found via
    # reproduction (a live run of this script) that reusing that exact cell here made
    # the lie's boost and the scent map's own boost at that cell stack on top of each
    # other, letting the lie win through fixture coincidence, not a mechanism bug — the
    # old language-based scent_report never asserted a boost at that exact cell (only
    # at a whole quadrant), so this coincidence was invisible before Revision 3.
    intent = decide_intent(lie_probability=1.0, rng=rng)
    lie_text = generate_hint(corroboration_true_pos, provider, config, intent)
    lie_focal_point = interpret_hint(lie_text, board)

    trail = ScentField.from_config(config)
    trail.advance(previous_pos, board)
    trail.advance(corroboration_true_pos, board)

    corroborated_belief = BeliefMap.uniform(board)
    corroborated_belief.update_from_hint(lie_focal_point, board)
    corroborated_belief.update_from_scent_map(trail.full_field(), board)
    print(f"    true position: {corroboration_true_pos}  (recent trail from {previous_pos})")
    print(f"    lying claim:   {lie_text!r} -> focal point {lie_focal_point}")
    print(f"    scent map:     {len(trail.full_field())} real cells -> argmax {corroborated_belief.most_likely_cell()}")
    lie_p = corroborated_belief.probability(lie_focal_point)
    truth_p = corroborated_belief.probability(corroboration_true_pos)
    print(
        f"    net belief: lie's region={lie_p:.4f}, true position={truth_p:.4f} "
        f"-> {'truth wins' if truth_p > lie_p else 'lie wins (unexpected)'}"
    )


def section_2_one_real_round_trip(config: GameConfig) -> None:
    print("\n2. One real round-trip — proving take_turn() pulls a real scent map and sends language, not coordinates")
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

        lines = client_log.read_text(encoding="utf-8").splitlines()
        hint_events = [line for line in lines if '"sending_hint"' in line]
        scent_events = [line for line in lines if '"scent_map_received"' in line]
        print(f"  after:  state={client.state_machine.state}, own_pos={client.game_state.own_pos}")
        print(f"  peer received and acked: {result}")
        print(f"  actual text that crossed the wire: {hint_events[0]}")
        print(f"  scent-map pull trace event: {scent_events[0]}")
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
