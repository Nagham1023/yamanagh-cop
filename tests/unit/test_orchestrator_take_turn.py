"""Orchestrator.take_turn (PRD 3): proves the brain is genuinely wired, not that
the algorithm works — algorithm correctness is reasoning/subgame.py's job
(PRD-3-blind-strategy.md, Design Question 3).
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

from cop.domain.board import Position
from cop.orchestrator import Orchestrator
from cop.reasoning.brain_base import BrainBase, Move
from cop.reasoning.cop_brain import CopBrain


class _AlwaysProposesAnOffBoardMove(BrainBase):
    """A deliberately buggy brain — proves take_turn() catches a brain/action
    failure the same way send_to_peer catches a network one, instead of
    stranding the state machine in COMPUTING_MOVE with nothing logged."""

    def _pick_move(self, own_pos, target_pos, board, barriers) -> str:
        return "N"

    def _decide_move(self, own_pos, target_pos, board, barriers) -> Move:
        return Move(direction="N")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_server(config, tmp_path, name: str) -> tuple[Orchestrator, int]:
    port = _free_port()
    server = Orchestrator(config, CopBrain(), log_path=str(tmp_path / f"{name}_trace.jsonl"))
    threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)
    return server, port


def test_take_turn_sends_the_brains_computed_position_not_a_caller_supplied_one(config, tmp_path):
    _, port = _start_server(config, tmp_path, "server")
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.game_state.own_pos = Position(3, 3)
    client.game_state.target_pos = Position(3, 0)  # due north — CopBrain must pick "N"

    result = asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    assert result == {"accepted": True, "col": 3, "row": 2}
    assert client.game_state.own_pos == Position(3, 2)
    assert client.state_machine.state == "WAITING_FOR_OPPONENT"


def test_take_turn_with_a_different_target_produces_a_different_outgoing_position(config, tmp_path):
    # The wiring-is-real proof: two otherwise-identical orchestrators with
    # different targets must send different coordinates — if take_turn()
    # silently ignored self.brain and sent a fixed position instead, this
    # would fail.
    _, port = _start_server(config, tmp_path, "server")

    north_client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "north_trace.jsonl"))
    north_client.game_state.own_pos = Position(3, 3)
    north_client.game_state.target_pos = Position(3, 0)

    east_client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "east_trace.jsonl"))
    east_client.game_state.own_pos = Position(3, 3)
    east_client.game_state.target_pos = Position(6, 3)

    north_result = asyncio.run(north_client.take_turn(f"http://127.0.0.1:{port}/mcp"))
    east_result = asyncio.run(east_client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    assert north_result != east_result
    assert north_result == {"accepted": True, "col": 3, "row": 2}
    assert east_result == {"accepted": True, "col": 4, "row": 3}


def test_take_turn_from_an_illegal_starting_state_raises_via_the_state_machine(config, tmp_path):
    _, port = _start_server(config, tmp_path, "server")
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.state_machine.state = "TECHNICAL_LOSS"  # terminal — nothing is legal from here

    try:
        asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))
        raised = False
    except ValueError:
        raised = True

    assert raised, "take_turn must not bypass rule 5's illegal-transition enforcement"


def test_take_turn_with_a_brain_that_proposes_an_illegal_action_reaches_technical_loss(
    config, tmp_path
):
    # cop_start is (0, 0) — "N" is off-board, so GameState.apply raises.
    # No live peer needed: this must fail before send_to_peer is ever called.
    client = Orchestrator(
        config, _AlwaysProposesAnOffBoardMove(), log_path=str(tmp_path / "trace.jsonl")
    )

    try:
        asyncio.run(client.take_turn("http://127.0.0.1:1/mcp"))
        raised = False
    except ValueError:
        raised = True

    assert raised
    assert client.state_machine.state == "TECHNICAL_LOSS"
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "technical_loss" in events
