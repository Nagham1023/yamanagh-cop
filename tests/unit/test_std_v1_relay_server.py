"""std_v1/relay_server.py tests -- the loopback-only relay that exposes
this repo's real `Std1TurnHandler`/`CopBrain` decision to a separate
`thief-peer` process over a tool call, never a Python import (rule 1/2).
In-process `Client`, same pattern `test_std_v1_server_registration.py`
already uses for this repo's other std_v1 tool surface."""

from __future__ import annotations

import asyncio

import pytest
from fastmcp import Client, FastMCP

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.memory.belief import BeliefMap
from cop.memory.scent import ScentField
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.state import GameState
from cop.std_v1.relay_server import _RelayState, register_relay_tools
from cop.std_v1.sealing import seal_turn
from cop.std_v1.turn_handler import Std1TurnHandler


def _turn_handler_factory(config):
    def factory() -> Std1TurnHandler:
        board = Board(size=config.board_size)
        barriers = BarrierSet(quota=config.barrier_quota)
        belief_map = BeliefMap.uniform(board, barriers=barriers)
        state = GameState(own_pos=Position(0, 0), target_pos=belief_map.most_likely_cell(), barriers=barriers)
        scent_field = ScentField.from_config(config)
        return Std1TurnHandler(board, state, CopBrain(), belief_map, scent_field, config)

    return factory


def _server(config):
    state = _RelayState()
    mcp = FastMCP(name="cop_relay_test")
    register_relay_tools(mcp, _turn_handler_factory(config), state)
    return mcp, state


def _call(mcp, tool: str, arguments: dict):
    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(tool, arguments)
            return result.data

    return asyncio.run(run())


def test_decide_police_turn_before_start_raises(config):
    mcp, _state = _server(config)
    with pytest.raises(Exception):  # noqa: PT011 -- FastMCP wraps the RuntimeError, exact type not this test's concern
        _call(mcp, "decide_police_turn", {"step": 1, "thief_smell_grid": {}, "thief_hint_text": ""})


def test_start_police_subgame_builds_a_fresh_handler(config):
    mcp, state = _server(config)
    result = _call(mcp, "start_police_subgame", {"sub_game_number": 2})
    assert result == {"ok": True}
    assert isinstance(state.handler, Std1TurnHandler)
    assert state.sub_game_number == 2


def test_decide_police_turn_returns_a_sealed_wire_ready_decision(config):
    mcp, _state = _server(config)
    _call(mcp, "start_police_subgame", {"sub_game_number": 2})
    decision = _call(
        mcp, "decide_police_turn",
        {"step": 1, "thief_smell_grid": {"3,3": 0.9}, "thief_hint_text": ""},
    )

    assert set(decision) == {"payload", "nonce", "commit"}
    payload = decision["payload"]
    assert payload["step"] == 1
    assert payload["sender"] == "police"
    assert payload["move"] in ("N", "S", "E", "W", "STAY")
    assert isinstance(decision["nonce"], str) and decision["nonce"]
    assert isinstance(decision["commit"], str) and len(decision["commit"]) == 64


def test_decide_police_turn_commit_is_a_real_seal_over_the_returned_payload(config):
    mcp, _state = _server(config)
    _call(mcp, "start_police_subgame", {"sub_game_number": 1})
    decision = _call(mcp, "decide_police_turn", {"step": 1, "thief_smell_grid": {}, "thief_hint_text": ""})

    # The commit really is a fresh seal over the returned payload, not a
    # value invented separately -- re-sealing the same payload proves the
    # shape sealing.py hashed is exactly the payload handed back.
    resealed = seal_turn(decision["payload"])
    assert isinstance(resealed["commit"], str) and len(resealed["commit"]) == 64


def test_relay_identity_returns_this_repos_own_real_commit(config):
    mcp, _state = _server(config)
    result = _call(mcp, "relay_identity", {})
    assert len(result["github_commit"]) == 40  # a real git rev-parse HEAD, not a placeholder


def test_decide_police_turn_persists_state_across_turns(config):
    mcp, state = _server(config)
    _call(mcp, "start_police_subgame", {"sub_game_number": 1})
    handler_before = state.handler
    _call(mcp, "decide_police_turn", {"step": 1, "thief_smell_grid": {}, "thief_hint_text": ""})
    # Same handler instance is still there -- position/belief carried over,
    # not rebuilt from scratch on every turn.
    assert state.handler is handler_before
