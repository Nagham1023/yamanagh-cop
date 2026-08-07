"""Orchestrator.take_turn (PRD 3): proves the brain is genuinely wired, not that
the algorithm works — algorithm correctness is reasoning/subgame.py's job
(PRD-3-blind-strategy.md, Design Question 3).

PRD 4 "Revision 3" (todoFullFix.md §C8): take_turn() now pulls the peer's
scent map via a Tool call *before* computing the move — every test that
calls take_turn() against a live peer now genuinely exercises that pull
too, not just the hint exchange.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

from cop.domain.board import Position
from cop.memory.belief import BeliefMap
from cop.orchestrator import Orchestrator
from cop.reasoning.brain_base import BrainBase, Move, PlaceBarrier
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.hint import interpret_hint
from cop.shared.private_config import PrivateConfig


class _AlwaysProposesAnOffBoardMove(BrainBase):
    """A deliberately buggy brain — proves take_turn() catches a brain/action
    failure the same way send_to_peer catches a network one, instead of
    stranding the state machine in COMPUTING_MOVE with nothing logged."""

    def _pick_move(self, own_pos, target_pos, board, barriers) -> str:
        return "N"

    def _decide_move(self, own_pos, target_pos, board, barriers) -> Move:
        return Move(direction="N")


class _AlwaysPlacesABarrierOnItsOwnCell(BrainBase):
    """todoFullFix.md §E1/§E2: a brain that always forgoes movement to
    place a barrier on its own current cell — proves take_turn() re-syncs
    BeliefMap's barrier-zero-belief after every placement, not just at
    construction."""

    def _pick_move(self, own_pos, target_pos, board, barriers) -> str:
        return "STAY"

    def _decide_move(self, own_pos, target_pos, board, barriers) -> PlaceBarrier:
        return PlaceBarrier(target=own_pos)


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


def _sent_hint_text(trace_path) -> str:
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    (sending_event,) = [e for e in events if e["event"] == "sending_hint"]
    return sending_event["text"]


def test_take_turn_moves_according_to_the_brains_own_decision_not_a_fixed_position(config, tmp_path):
    # The ack (`{"accepted": bool, "word_count": int}`) no longer echoes back
    # enough to distinguish outcomes by content — PRD 4's wire protocol is
    # language, not a position round-trip. Observe the client's own state
    # and trace log instead, same as PRD 3's discipline, adapted to what's
    # actually observable now.
    _, port = _start_server(config, tmp_path, "server")
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.game_state.own_pos = Position(3, 3)
    client.game_state.target_pos = Position(3, 0)  # due north — CopBrain must pick "N"

    result = asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    assert result["accepted"] is True
    assert result["word_count"] == len(_sent_hint_text(tmp_path / "client_trace.jsonl").split())
    assert client.game_state.own_pos == Position(3, 2)
    assert client.state_machine.state == "WAITING_FOR_OPPONENT"


def test_take_turn_with_a_different_target_produces_a_different_outgoing_position(config, tmp_path):
    # The wiring-is-real proof: two otherwise-identical orchestrators with
    # different targets must apply different moves and send different hint
    # text — if take_turn() silently ignored self.brain and sent a fixed
    # position instead, this would fail.
    _, port = _start_server(config, tmp_path, "server")

    north_client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "north_trace.jsonl"))
    north_client.game_state.own_pos = Position(3, 3)
    north_client.game_state.target_pos = Position(3, 0)

    east_client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "east_trace.jsonl"))
    east_client.game_state.own_pos = Position(3, 3)
    east_client.game_state.target_pos = Position(6, 3)

    asyncio.run(north_client.take_turn(f"http://127.0.0.1:{port}/mcp"))
    asyncio.run(east_client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    assert north_client.game_state.own_pos == Position(3, 2)
    assert east_client.game_state.own_pos == Position(4, 3)
    north_text = _sent_hint_text(tmp_path / "north_trace.jsonl")
    east_text = _sent_hint_text(tmp_path / "east_trace.jsonl")
    assert north_text != east_text


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
    # A real live peer is needed here now: take_turn() pulls the peer's
    # scent map *before* computing the move (todoFullFix.md §C4's
    # ordering) — without one, the failure would be a network error, not
    # this brain bug.
    _, port = _start_server(config, tmp_path, "server")
    client = Orchestrator(
        config, _AlwaysProposesAnOffBoardMove(), log_path=str(tmp_path / "trace.jsonl")
    )

    try:
        asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))
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


def test_take_turn_against_an_unreachable_peer_reaches_technical_loss_before_computing_a_move(
    config, tmp_path
):
    # The new failure mode PRD 4 "Revision 3" introduces: the scent-map
    # pull happens first, so an unreachable peer must fail there, before
    # the brain (a perfectly legal one here) ever gets a chance to run.
    dead_url = f"http://127.0.0.1:{_free_port()}/mcp"  # nothing listens here
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))

    try:
        asyncio.run(client.take_turn(dead_url))
        raised = False
    except Exception:  # noqa: BLE001 - any connection failure counts
        raised = True

    assert raised
    assert client.state_machine.state == "TECHNICAL_LOSS"
    assert client.game_state.own_pos == Position(*config.cop_start), "must not have moved at all"


def test_take_turn_updates_belief_map_and_scent_field_not_just_game_state(config, tmp_path):
    _, port = _start_server(config, tmp_path, "server")
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    belief_before = client.belief_map.probability(client.game_state.own_pos)
    scent_before = client.scent_field.sample(client.game_state.own_pos, client.board)

    asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    assert client.belief_map.probability(client.game_state.own_pos) != belief_before
    assert client.scent_field.sample(client.game_state.own_pos, client.board) != scent_before


def test_take_turn_zeroes_belief_at_a_newly_placed_barrier(config, tmp_path):
    # todoFullFix.md §E1: "whenever the barrier set changes," not just at
    # construction — placing a barrier this turn must immediately zero the
    # belief map's own probability there, live, not only after a fresh
    # BeliefMap gets built.
    _, port = _start_server(config, tmp_path, "server")
    client = Orchestrator(
        config, _AlwaysPlacesABarrierOnItsOwnCell(), log_path=str(tmp_path / "client_trace.jsonl")
    )
    own_pos = client.game_state.own_pos
    assert client.belief_map.probability(own_pos) > 0.0

    asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    assert own_pos in client.game_state.barriers.placed
    assert client.belief_map.probability(own_pos) == 0.0
    assert client.belief_map.most_likely_cell() != own_pos


def test_take_turn_logs_the_intent_flag(config, tmp_path):
    _, port = _start_server(config, tmp_path, "server")
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))

    asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    events = [
        json.loads(line)
        for line in (tmp_path / "client_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (hint_event,) = [e for e in events if e["event"] == "hint_generated"]
    assert hint_event["intent"] in (True, False)


def test_take_turn_pulls_and_applies_the_peers_real_scent_map(config, tmp_path):
    # PRD 4 "Revision 3": take_turn() must genuinely call the peer's
    # share_scent_map tool and fold real numeric data into belief — not a
    # fixed placeholder or a skipped step. The server's own ScentField is
    # primed with a real trail so there's something nonzero to pull and
    # observe the effect of.
    server, port = _start_server(config, tmp_path, "server")
    server.scent_field.advance(Position(6, 6), server.board)

    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    belief_before = client.belief_map.probability(Position(6, 6))

    asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    assert client.belief_map.probability(Position(6, 6)) > belief_before
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "client_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "requesting_scent_map" in events
    assert "scent_map_received" in events


def test_on_hint_received_applies_the_tactical_claim(config, tmp_path):
    # PRD 4 "Revision 3": _on_hint_received now only ever sees the tactical
    # hint — scent-map corroboration moved to take_turn's own pull.
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    claim_focal = interpret_hint("Near the south east side.", client.board)
    claim_before = client.belief_map.probability(claim_focal)

    client._on_hint_received("Near the south east side.")

    assert client.belief_map.probability(claim_focal) > claim_before


def test_on_hint_received_does_not_apply_an_over_limit_claim(config, tmp_path):
    # rule-auditor finding (I9): receive_hint's ack flags an over-limit
    # hint to the sender, but the ack alone doesn't stop the *content* from
    # reaching this callback — it must be gated before touching belief
    # state. Compared against a control BeliefMap that's never updated at
    # all: if the over-limit claim contributed nothing, the two end up
    # byte-identical.
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    over_limit_text = " ".join(["south", "east"] * config.hint_word_limit)

    control = BeliefMap.uniform(client.board)

    client._on_hint_received(over_limit_text)

    assert client.belief_map._probabilities == control._probabilities


def _private_config_pointing_at(port: int) -> PrivateConfig:
    """todoFullFix.md §B3: a PrivateConfig whose [network].opponent_url
    points at a real running peer, for proving take_turn() falls back to it."""
    return PrivateConfig(
        provider="template", every_n_steps=1,
        opponent_url=f"http://127.0.0.1:{port}/mcp", my_port=0, turn_timeout_seconds=180.0,
        group_name="dev-team", group_id="dev-team", sub_game_number=1, members=("dev-1",),
        repos={"cop": "https://example.com/cop", "thief": "https://example.com/thief"},
        model="claude-sonnet-5", step_deadline_seconds=30.0,
        email_recipient="dev@example.com", email_mode="draft",
    )


def test_take_turn_without_an_explicit_peer_url_uses_the_private_configs_opponent_url(config, tmp_path):
    _, port = _start_server(config, tmp_path, "server")
    client = Orchestrator(
        config, CopBrain(),
        log_path=str(tmp_path / "client_trace.jsonl"),
        private_config=_private_config_pointing_at(port),
    )

    result = asyncio.run(client.take_turn())  # no peer_url argument at all

    assert result["accepted"] is True
    assert client.state_machine.state == "WAITING_FOR_OPPONENT"
