"""`play_game()` (PRD 8): the first live, multi-turn loop in this repo.
Every fixture here plays the peer with a raw FastMCP server (this repo can
never run a thief brain, rule 1/2), same discipline as
`test_orchestrator_capture.py`.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

from fastmcp import FastMCP

from cop.domain.board import Position
from cop.domain.scoring import Outcome
from cop.orchestrator import Orchestrator
from cop.reasoning.cop_brain import CopBrain
from cop.tools.mcp_client_prd6 import send_capture_response


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_confirming_thief_peer(client_url: str) -> int:
    """Acks commit/reveal/scent normally; confirms every capture claim."""
    mcp = FastMCP("confirming_thief_peer")

    @mcp.tool
    def receive_commit(h_commit: str) -> dict:
        return {"acknowledged": True}

    @mcp.tool
    def receive_reveal(move: dict, hint_text: str) -> dict:
        return {"accepted": True, "word_count": len(hint_text.split())}

    @mcp.tool
    def share_scent_map() -> dict:
        return {"cells": []}

    @mcp.tool
    def receive_capture_claim(
        thief_col: int, thief_row: int, cop_col: int, cop_row: int, claimed_at_step: int
    ) -> dict:
        def _respond() -> None:
            asyncio.run(send_capture_response(client_url, True, thief_col, thief_row))

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


def _start_denying_thief_peer(client_url: str) -> int:
    """Acks commit/reveal/scent/barrier-declaration normally over several
    real turns (CopBrain can legitimately choose `PlaceBarrier`, not just
    `Move`, found only by actually running multiple real turns — no prior
    test in this repo ran CopBrain this many real turns against a minimal
    fake peer); denies any capture claim that happens to arrive (CopBrain's
    own barrier logic can also legitimately land a barrier on the belief
    target) rather than leaving no `receive_capture_claim` tool at all,
    which would fail the wire call outright, or leaving one that never
    answers, which would hang."""
    mcp = FastMCP("denying_thief_peer")

    @mcp.tool
    def receive_commit(h_commit: str) -> dict:
        return {"acknowledged": True}

    @mcp.tool
    def receive_reveal(move: dict, hint_text: str) -> dict:
        return {"accepted": True, "word_count": len(hint_text.split())}

    @mcp.tool
    def share_scent_map() -> dict:
        return {"cells": []}

    @mcp.tool
    def receive_barrier_declaration(col: int, row: int) -> dict:
        return {"acknowledged": True}

    @mcp.tool
    def receive_capture_claim(
        thief_col: int, thief_row: int, cop_col: int, cop_row: int, claimed_at_step: int
    ) -> dict:
        def _respond() -> None:
            asyncio.run(send_capture_response(client_url, False, thief_col, thief_row))

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


def _start_client(config, tmp_path) -> tuple[Orchestrator, str]:
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    port = _free_port()
    client_url = f"http://127.0.0.1:{port}/mcp"
    threading.Thread(
        target=client.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)
    return client, client_url


def test_play_game_stops_the_instant_capture_is_confirmed_no_extra_turn(config, tmp_path):
    client, client_url = _start_client(config, tmp_path)
    thief_port = _start_confirming_thief_peer(client_url)

    # Rigged so turn 1's move lands exactly on the belief target.
    client.game_state.target_pos = Position(1, 0)
    client.belief_map.most_likely_cell = lambda: Position(1, 0)

    outcome = asyncio.run(client.play_game(f"http://127.0.0.1:{thief_port}/mcp"))

    assert outcome == Outcome.CAPTURE
    assert client.game_state.steps_taken == 1  # exactly one turn, not a second


def test_play_game_reaches_survival_at_the_step_ceiling(config, tmp_path):
    fast_config = config.__class__(**{**config.__dict__, "step_ceiling": 2, "survival_threshold": 100})
    client, client_url = _start_client(fast_config, tmp_path)
    thief_port = _start_denying_thief_peer(client_url)

    outcome = asyncio.run(client.play_game(f"http://127.0.0.1:{thief_port}/mcp"))

    assert outcome == Outcome.SURVIVAL
    assert client.game_state.steps_taken == 2


def test_play_game_calls_watchdog_heartbeat_once_per_completed_turn(config, tmp_path, monkeypatch):
    fast_config = config.__class__(**{**config.__dict__, "step_ceiling": 3, "survival_threshold": 100})
    client, client_url = _start_client(fast_config, tmp_path)
    thief_port = _start_denying_thief_peer(client_url)

    heartbeats = []
    monkeypatch.setattr(client.watchdog, "heartbeat", lambda: heartbeats.append(1))

    asyncio.run(client.play_game(f"http://127.0.0.1:{thief_port}/mcp"))

    # play_game heartbeats once per completed turn; inbound peer tool calls
    # (rule 7 / _on_connection_received) also heartbeat — with rule-46
    # barrier Capture Claims that adds ≥1 extra beat, so assert the floor.
    assert client.game_state.steps_taken == 3
    assert len(heartbeats) >= 3


def test_play_game_converts_a_technical_loss_into_a_return_value_not_an_exception(config, tmp_path):
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    dead_url = f"http://127.0.0.1:{_free_port()}/mcp"  # nothing listens here

    outcome = asyncio.run(client.play_game(dead_url))

    assert outcome == Outcome.TECHNICAL_LOSS
    assert client.state_machine.state == "TECHNICAL_LOSS"


def test_play_game_stamps_started_and_ended_at_on_an_ordinary_outcome(config, tmp_path):
    fast_config = config.__class__(**{**config.__dict__, "step_ceiling": 1, "survival_threshold": 100})
    client, client_url = _start_client(fast_config, tmp_path)
    thief_port = _start_denying_thief_peer(client_url)

    assert client._match_started_at is None
    assert client._match_ended_at is None

    asyncio.run(client.play_game(f"http://127.0.0.1:{thief_port}/mcp"))

    assert client._match_started_at is not None
    assert client._match_ended_at is not None
    assert client._match_started_at <= client._match_ended_at  # ISO-8601 sorts lexically


def test_play_game_stamps_started_and_ended_at_even_on_a_technical_loss(config, tmp_path):
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    dead_url = f"http://127.0.0.1:{_free_port()}/mcp"  # nothing listens here

    asyncio.run(client.play_game(dead_url))

    assert client._match_started_at is not None
    assert client._match_ended_at is not None


def test_play_game_with_enable_gui_true_updates_and_closes_window(config, tmp_path, monkeypatch):
    fast_config = config.__class__(**{**config.__dict__, "step_ceiling": 1, "survival_threshold": 100})
    client, client_url = _start_client(fast_config, tmp_path)
    thief_port = _start_denying_thief_peer(client_url)

    updates = []
    closed = []

    class DummyGuiWindow:
        def __init__(self, board_size: int):
            pass

        def update(self, rendered):
            updates.append(rendered)

        def close(self):
            closed.append(True)

    monkeypatch.setattr("cop.orchestrator_game_loop.LiveGuiWindow", DummyGuiWindow)

    outcome = asyncio.run(client.play_game(f"http://127.0.0.1:{thief_port}/mcp", enable_gui=True))

    assert outcome == Outcome.SURVIVAL
    # Immediate paint on open + one post-turn update (blank-window fix).
    assert len(updates) == 2
    assert closed == [True]


def test_play_game_stops_when_peer_sends_final_reveal_ch532(config, tmp_path):
    # Ch.5.3.2 Step 4: Final Reveal = end of game. Without this stop, a peer
    # that ends early leaves Cop looping to the ceiling (rule 35 risk).
    fast_config = config.__class__(**{**config.__dict__, "step_ceiling": 20, "survival_threshold": 100})
    client, client_url = _start_client(fast_config, tmp_path)
    thief_port = _start_denying_thief_peer(client_url)

    async def _run() -> Outcome:
        async def _end_after_first_turn(peer_url: str):
            await original_take_turn(peer_url)
            client._on_final_reveal_received({"1": "deadbeef"}, {"1": True})

        original_take_turn = client.take_turn
        client.take_turn = _end_after_first_turn  # type: ignore[method-assign]
        return await client.play_game(f"http://127.0.0.1:{thief_port}/mcp")

    outcome = asyncio.run(_run())

    assert client._peer_final_reveal_received is True
    assert outcome == Outcome.TECHNICAL_LOSS
    assert client.game_state.steps_taken == 1


def test_play_game_peer_final_reveal_preserves_confirmed_capture(config, tmp_path):
    client, client_url = _start_client(config, tmp_path)
    thief_port = _start_confirming_thief_peer(client_url)
    client.game_state.target_pos = Position(1, 0)
    client.belief_map.most_likely_cell = lambda: Position(1, 0)

    async def _run() -> Outcome:
        async def _capture_then_peer_reveal(peer_url: str):
            await original_take_turn(peer_url)
            client._on_final_reveal_received({"1": "deadbeef"}, {"1": True})

        original_take_turn = client.take_turn
        client.take_turn = _capture_then_peer_reveal  # type: ignore[method-assign]
        return await client.play_game(f"http://127.0.0.1:{thief_port}/mcp")

    outcome = asyncio.run(_run())

    assert outcome == Outcome.CAPTURE
    assert client._last_turn_captured is True

