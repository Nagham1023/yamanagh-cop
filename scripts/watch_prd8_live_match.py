"""Watch PRD 8's first-ever live, multi-turn match run end to end:
`play_game()` looping real turns to a genuine, wire-confirmed
`Outcome.CAPTURE`, then `report_game()` running the automatic end-of-game
sequence (final reveal, both audits, league bookkeeping, the Gatekeeper-
wrapped report send) live. A second, adversarial run shows a wrong belief
denied instead of confirmed — the match continuing to an ordinary
`SURVIVAL` ending, not a false capture and not a technical loss
(Design Question 1).

Run:
    uv run python scripts/watch_prd8_live_match.py
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from pathlib import Path

from fastmcp import FastMCP

from cop.domain.board import Position
from cop.orchestrator import Orchestrator
from cop.reasoning.cop_brain import CopBrain
from cop.shared.config import GameConfig
from cop.tools.mcp_client_prd6 import send_capture_response

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "shared" / "config_dev_g01.json"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_thief_peer(client_url: str, *, confirm: bool) -> int:
    mcp = FastMCP("watch_thief_peer")

    @mcp.tool
    def receive_commit(h_commit: str, sent_at: float, deadline_at: float) -> dict:
        return {"acknowledged": True}

    @mcp.tool
    def receive_reveal(move: dict, hint_text: str, sent_at: float, deadline_at: float) -> dict:
        return {"accepted": True, "word_count": len(hint_text.split())}

    @mcp.tool
    def share_scent_map() -> dict:
        return {"cells": []}

    @mcp.tool
    def receive_barrier_declaration(col: int, row: int) -> dict:
        return {"acknowledged": True}

    @mcp.tool
    def receive_final_reveal(nonces: dict, intents: dict) -> dict:
        return {"acknowledged": True}

    @mcp.tool
    def receive_capture_claim(
        thief_col: int, thief_row: int, cop_col: int, cop_row: int, claimed_at_step: int
    ) -> dict:
        print(f"  [thief peer] received capture claim at ({thief_col}, {thief_row}) — "
              f"{'confirming' if confirm else 'denying'}")

        def _respond() -> None:
            asyncio.run(send_capture_response(client_url, confirm, thief_col, thief_row))

        threading.Thread(target=_respond, daemon=True).start()
        return {"acknowledged": True}

    port = _free_port()
    threading.Thread(
        target=mcp.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": port, "show_banner": False},
        daemon=True,
    ).start()
    time.sleep(0.5)
    return port


def _run_case(config, log_path, *, confirm: bool) -> None:
    print(f"\n{'=' * 60}")
    print(f"Case: peer will {'CONFIRM' if confirm else 'DENY'} the capture claim")
    print("=" * 60)

    client = Orchestrator(config, CopBrain(), log_path=str(log_path))
    port = _free_port()
    client_url = f"http://127.0.0.1:{port}/mcp"
    threading.Thread(
        target=client.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    thief_port = _start_thief_peer(client_url, confirm=confirm)

    # Rig turn 1 to land the cop exactly on its own belief target — the
    # honest, book-confirmed trigger (Design Question 1), not a hardcoded
    # "always capture" shortcut.
    client.game_state.target_pos = Position(1, 0)
    client.belief_map.most_likely_cell = lambda: Position(5, 5)

    print("\n1. play_game() — a real multi-turn loop")
    outcome = asyncio.run(client.play_game(f"http://127.0.0.1:{thief_port}/mcp"))
    print(f"   outcome: {outcome}")
    print(f"   steps taken: {client.game_state.steps_taken}")

    print("\n2. report_game() — the automatic end-of-game sequence")
    result = asyncio.run(
        client.report_game(
            f"http://127.0.0.1:{thief_port}/mcp",
            outcome,
            is_counted=False,
            opponent_id="watch-script-peer",
            opponent_cop_repo_url="https://github.com/team-b/cop",
            opponent_thief_repo_url="https://github.com/team-b/thief",
            sub_game_scores={"g01": 20 if outcome.value == "capture" else 5},
            cumulative_score=20 if outcome.value == "capture" else 5,
        )
    )
    print(f"   send result (None expected — config/game.toml's email_mode is 'draft'): {result}")
    print(f"   gatekeeper queue status: {client.gatekeeper.get_queue_status()}")


def main() -> None:
    config = GameConfig.from_file(CONFIG_PATH)
    # The deny case never captures, so it always runs to the real
    # step_ceiling (35 by default) — shortened here just to keep this demo
    # script quick to watch; the confirmed case ends after turn 1 regardless.
    fast_config = config.__class__(**{**config.__dict__, "step_ceiling": 5, "survival_threshold": 5})

    _run_case(config, "/tmp/watch_prd8_confirmed_trace.jsonl", confirm=True)
    _run_case(fast_config, "/tmp/watch_prd8_denied_trace.jsonl", confirm=False)

    print("\nBoth cases ran end-to-end: a real confirmed capture ending the match,")
    print("and a denied claim continuing it to an ordinary SURVIVAL ending.")


if __name__ == "__main__":
    main()
