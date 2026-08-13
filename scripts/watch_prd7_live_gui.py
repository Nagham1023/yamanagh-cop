"""Watch PRD 7's Live GUI milestone run live: two real Orchestrators
exchanging turns, the GUI window updating on each turn from real belief-map
state — never the true opponent position (rules 8/9).

Run:
    uv run python scripts/watch_prd7_live_gui.py
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from pathlib import Path

from cop.observability.live_gui import LiveGuiWindow, render_state
from cop.orchestrator import Orchestrator
from cop.reasoning.cop_brain import CopBrain
from cop.shared.config import GameConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "shared" / "config_dev_g01.json"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> None:
    config = GameConfig.from_file(CONFIG_PATH)
    log_path = Path("/tmp/watch_prd7_live_gui_trace.jsonl")
    log_path.unlink(missing_ok=True)

    print("1. Two real OS-thread peers, a real belief-map GUI window")
    port = _free_port()
    server = Orchestrator(config, CopBrain(), log_path=str(log_path.with_suffix(".server.jsonl")))
    threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    client = Orchestrator(config, CopBrain(), log_path=str(log_path))
    window = LiveGuiWindow(board_size=config.board_size)

    try:
        for turn in range(3):
            print(f"\n2.{turn} take_turn() — a real commit/reveal round trip")
            asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

            rendered = render_state(
                client.game_state.own_pos,
                client.belief_map._probabilities,
                client.state_machine.state,
                frozenset(client.game_state.barriers.placed),
                client.scent_field.full_field(),
                client._last_hint_received,
            )
            window.update(rendered)
            print(f"  own_pos={rendered.own_pos}  banner={rendered.banner_text!r}")
            print(f"  belief cells rendered: {len(rendered.grid_colors)}")
            print(f"  most_likely_pos (star): {rendered.most_likely_pos}")
            print(f"  barriers placed (dark squares): {sorted(rendered.barrier_positions)}")
            print(f"  scent cells sensed (blue grid): {len(rendered.scent_grid_colors)}")
            # client only ever *sends* reveals in this one-directional demo
            # (it calls take_turn every round, server never does) — so
            # client._last_hint_received honestly stays None throughout;
            # the real round-trip is covered by test_orchestrator_take_turn.py.
            print(f"  last hint received: {rendered.hint_text!r}")
            print(
                "  rule 8/9 check: render_state's own signature admits no true "
                "opponent position or Board — see test_live_gui.py's own guard test"
            )
    finally:
        window.close()

    print("\nAll PRD 7 Live GUI milestone behaviours ran end-to-end.")


if __name__ == "__main__":
    main()
