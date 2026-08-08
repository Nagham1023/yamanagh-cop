"""`_claim_capture_if_warranted` (PRD 8, rules 21/22): wired inside
`commit_and_reveal_to_peer`'s own `AWAITING_REVEAL` window (Design Question
2's corrected design — no new state-machine state).

This repo can never run a thief brain (rule 1/2), and the client's own
server-side `_on_capture_claim_received` is a deliberate no-op (Design
Question 3) — so every fixture here plays the "honest/dishonest thief"
role with a raw FastMCP server, not a second `Orchestrator`, and that fake
peer calls `send_capture_response` back to the client's own known address
itself (the same "each side already knows its peer's static address"
assumption every other wire exchange in this repo already relies on).
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest
from fastmcp import FastMCP

from cop.domain.board import Position
from cop.orchestrator import Orchestrator
from cop.reasoning.brain_base import Move
from cop.reasoning.cop_brain import CopBrain
from cop.tools.mcp_client_prd6 import send_capture_response


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_thief_peer(client_url: str, *, confirm: bool) -> int:
    """A raw FastMCP server standing in for the thief peer — acks
    commit/reveal normally, and on a capture claim, calls back
    `send_capture_response` to `client_url` itself (confirming or denying,
    per `confirm`) from a background thread, mirroring the real, genuinely
    asynchronous claim/response shape (Design Question 2)."""
    mcp = FastMCP("thief_peer")

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


def test_a_move_landing_on_the_belief_target_claims_and_gets_confirmed(config, tmp_path):
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    port = _free_port()
    client_url = f"http://127.0.0.1:{port}/mcp"
    threading.Thread(
        target=client.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    thief_port = _start_thief_peer(client_url, confirm=True)
    move = Move(direction="E")
    believed_thief_pos = Position(1, 0)  # where the move lands
    client.game_state.apply(move, client.board)
    client.state_machine.transition("COMPUTING_MOVE")

    asyncio.run(
        client.commit_and_reveal_to_peer(
            f"http://127.0.0.1:{thief_port}/mcp",
            move,
            False,
            "quiet by the river",
            believed_thief_pos,
        )
    )

    assert client._last_turn_captured is True
    assert client.state_machine.state == "WAITING_FOR_OPPONENT"


def test_a_wrong_belief_gets_denied_and_the_game_continues_normally(config, tmp_path):
    """The single most important test in this section (Design Question 1):
    a claim built from a wrong belief is not a rule 21 violation and not a
    technical loss — just an ordinary, denied claim."""
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    port = _free_port()
    client_url = f"http://127.0.0.1:{port}/mcp"
    threading.Thread(
        target=client.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    thief_port = _start_thief_peer(client_url, confirm=False)
    move = Move(direction="E")
    believed_thief_pos = Position(1, 0)
    client.game_state.apply(move, client.board)
    client.state_machine.transition("COMPUTING_MOVE")

    asyncio.run(
        client.commit_and_reveal_to_peer(
            f"http://127.0.0.1:{thief_port}/mcp",
            move,
            False,
            "quiet by the river",
            believed_thief_pos,
        )
    )

    assert client._last_turn_captured is False
    assert client.state_machine.state == "WAITING_FOR_OPPONENT"


def test_no_claim_sent_when_the_move_does_not_land_on_the_belief_target(config, tmp_path):
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    port = _free_port()
    threading.Thread(
        target=client.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    claims_seen = []
    mcp = FastMCP("thief_peer_no_claim_expected")

    @mcp.tool
    def receive_commit(h_commit: str) -> dict:
        return {"acknowledged": True}

    @mcp.tool
    def receive_reveal(move: dict, hint_text: str) -> dict:
        return {"accepted": True, "word_count": len(hint_text.split())}

    @mcp.tool
    def receive_capture_claim(
        thief_col: int, thief_row: int, cop_col: int, cop_row: int, claimed_at_step: int
    ) -> dict:
        claims_seen.append((thief_col, thief_row))
        return {"acknowledged": True}

    thief_port = _free_port()
    threading.Thread(
        target=mcp.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": thief_port, "show_banner": False},
        daemon=True,
    ).start()
    time.sleep(0.5)

    move = Move(direction="E")
    client.game_state.apply(move, client.board)
    client.state_machine.transition("COMPUTING_MOVE")

    asyncio.run(
        client.commit_and_reveal_to_peer(
            f"http://127.0.0.1:{thief_port}/mcp",
            move,
            False,
            "quiet by the river",
            None,  # no belief target passed at all — the common case
        )
    )

    assert claims_seen == []
    assert client._last_turn_captured is False


def test_a_peer_that_never_responds_to_a_claim_reaches_technical_loss_via_awaiting_reveal(
    config, tmp_path
):
    # A short timeout — the default 30s would make this test needlessly
    # slow for a deadline this test wants to actually hit for real.
    fast_config = config.__class__(**{**config.__dict__, "response_timeout_seconds": 0.5})
    client = Orchestrator(fast_config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    port = _free_port()
    threading.Thread(
        target=client.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    mcp = FastMCP("silent_thief_peer")

    @mcp.tool
    def receive_commit(h_commit: str) -> dict:
        return {"acknowledged": True}

    @mcp.tool
    def receive_reveal(move: dict, hint_text: str) -> dict:
        return {"accepted": True, "word_count": len(hint_text.split())}

    @mcp.tool
    def receive_capture_claim(
        thief_col: int, thief_row: int, cop_col: int, cop_row: int, claimed_at_step: int
    ) -> dict:
        return {"acknowledged": True}  # acks, never calls send_capture_response back

    thief_port = _free_port()
    threading.Thread(
        target=mcp.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": thief_port, "show_banner": False},
        daemon=True,
    ).start()
    time.sleep(0.5)

    move = Move(direction="E")
    believed_thief_pos = Position(1, 0)
    client.game_state.apply(move, client.board)
    client.state_machine.transition("COMPUTING_MOVE")

    with pytest.raises(Exception):  # noqa: B017 - any deadline/connection failure counts
        asyncio.run(
            client.commit_and_reveal_to_peer(
                f"http://127.0.0.1:{thief_port}/mcp",
                move,
                False,
                "quiet by the river",
                believed_thief_pos,
            )
        )

    assert client.state_machine.state == "TECHNICAL_LOSS"


def test_take_turn_claims_using_the_belief_that_decided_this_move_not_next_turns(config, tmp_path):
    """PRD 8's own Finding 2, exercised through the real `take_turn()` path
    this time (every other test in this file calls `commit_and_reveal_to_peer`
    directly with an explicit `believed_thief_pos`, which never actually
    proves `take_turn()` itself captures the value at the right moment).
    `target_pos` is pre-seeded so the brain decides this turn's move toward
    it; `belief_map.most_likely_cell` is monkeypatched to return a
    *different* cell for whatever belief update happens after the move is
    applied — if `take_turn()` read `self.game_state.target_pos` directly
    instead of capturing it before that overwrite, the claim would compare
    against the wrong (already-updated) cell and never fire at all."""
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    port = _free_port()
    client_url = f"http://127.0.0.1:{port}/mcp"
    threading.Thread(
        target=client.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    thief_port = _start_thief_peer(client_url, confirm=True)

    client.game_state.target_pos = Position(1, 0)  # CopBrain moves E from (0,0) to reach this
    client.belief_map.most_likely_cell = lambda: Position(5, 5)  # next turn's belief, post-move

    asyncio.run(client.take_turn(f"http://127.0.0.1:{thief_port}/mcp"))

    assert client.game_state.own_pos == Position(1, 0)
    assert client._last_turn_captured is True


def test_a_peer_lacking_the_capture_claim_tool_reaches_technical_loss_on_the_send_itself(
    config, tmp_path
):
    """Distinct from the 'acks but never responds' test above: here the
    claim *send* itself fails (no such tool on the peer at all), not the
    later wait on a response — the earlier except block (around the
    `send_capture_claim` call), not the later one (around the response
    wait)."""
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    port = _free_port()
    threading.Thread(
        target=client.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    mcp = FastMCP("no_capture_tool_peer")

    @mcp.tool
    def receive_commit(h_commit: str) -> dict:
        return {"acknowledged": True}

    @mcp.tool
    def receive_reveal(move: dict, hint_text: str) -> dict:
        return {"accepted": True, "word_count": len(hint_text.split())}

    thief_port = _free_port()
    threading.Thread(
        target=mcp.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": thief_port, "show_banner": False},
        daemon=True,
    ).start()
    time.sleep(0.5)

    move = Move(direction="E")
    believed_thief_pos = Position(1, 0)
    client.game_state.apply(move, client.board)
    client.state_machine.transition("COMPUTING_MOVE")

    with pytest.raises(Exception):  # noqa: B017 - any tool-call failure counts
        asyncio.run(
            client.commit_and_reveal_to_peer(
                f"http://127.0.0.1:{thief_port}/mcp",
                move,
                False,
                "quiet by the river",
                believed_thief_pos,
            )
        )

    assert client.state_machine.state == "TECHNICAL_LOSS"


def test_on_capture_response_received_sets_both_response_and_event(config, tmp_path):
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    loop = asyncio.new_event_loop()
    client._capture_response_loop = loop
    try:
        client._on_capture_response_received(True, 3, 4)
        # call_soon_threadsafe only *queues* the callback — the loop must
        # actually run once for it to execute, same as it would under a
        # real run_as_server thread's own event loop.
        loop.run_until_complete(asyncio.sleep(0))
    finally:
        loop.close()

    assert client._capture_response is not None
    assert client._capture_response.confirmed is True
    assert client._capture_response.true_thief_pos == Position(3, 4)
    assert client._capture_response_event.is_set()


def test_on_capture_claim_received_never_raises_never_sends_a_response(config, tmp_path):
    """Design Question 3's rejection test: this repo's own role never
    legitimately receives a claim — a defensive no-op, not a fabricated
    `CaptureResponse` about a position this process cannot honestly assert."""
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))

    client._on_capture_claim_received(3, 3, 0, 0, 1)  # must not raise

    assert client._capture_response is None
    assert not client._capture_response_event.is_set()
