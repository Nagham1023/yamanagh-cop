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
from cop.memory.belief import BeliefMap
from cop.orchestrator import Orchestrator
from cop.reasoning.brain_base import BrainBase, Move
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.hint import interpret_hint


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


def _sent_hint_text(trace_path) -> str:
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    (sending_event,) = [e for e in events if e["event"] == "sending_hint"]
    return sending_event["text"]


def _sent_scent_report(trace_path) -> str:
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    (sending_event,) = [e for e in events if e["event"] == "sending_hint"]
    return sending_event["scent_report"]


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


def test_take_turn_updates_belief_map_and_scent_field_not_just_game_state(config, tmp_path):
    _, port = _start_server(config, tmp_path, "server")
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    belief_before = client.belief_map.probability(client.game_state.own_pos)
    scent_before = client.scent_field.sample(client.game_state.own_pos, client.board)

    asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    assert client.belief_map.probability(client.game_state.own_pos) != belief_before
    assert client.scent_field.sample(client.game_state.own_pos, client.board) != scent_before


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


def test_take_turn_sends_the_generated_scent_report_alongside_the_claim(config, tmp_path):
    # Revision 1: the scent report is a real, second field on the wire, not
    # just an ack detail — proves take_turn() actually generates and sends
    # it, not a fixed/placeholder string, same "wiring is real" discipline
    # the tactical hint already gets.
    _, port = _start_server(config, tmp_path, "server")
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))

    asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    scent_report_text = _sent_scent_report(tmp_path / "client_trace.jsonl")
    assert scent_report_text.startswith("Scent strongest to the")


def test_on_hint_received_applies_both_the_claim_and_the_scent_report(config, tmp_path):
    # The receiving side of Revision 1's corroboration mechanic: both
    # channels measurably update belief, at their own trust weight — not
    # just the tactical claim as PRD 4's original build did.
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    claim_focal = interpret_hint("Near the south east side.", client.board)
    scent_focal = interpret_hint("Scent strongest to the north west.", client.board)
    claim_before = client.belief_map.probability(claim_focal)
    scent_before = client.belief_map.probability(scent_focal)

    client._on_hint_received("Near the south east side.", "Scent strongest to the north west.")

    assert client.belief_map.probability(claim_focal) > claim_before
    assert client.belief_map.probability(scent_focal) > scent_before
    # The scent report's guaranteed-truthful boost outweighs the claim's.
    assert client.belief_map.probability(scent_focal) > client.belief_map.probability(claim_focal)


def test_on_hint_received_does_not_apply_an_over_limit_claim(config, tmp_path):
    # rule-auditor finding (I9): receive_hint's ack flags an over-limit
    # field to the sender, but the ack alone doesn't stop the *content* from
    # reaching this callback — each field must be gated independently
    # before it touches belief state. Compared against a control BeliefMap
    # that only ever received the (still-valid) scent-report update: if the
    # over-limit claim contributed nothing, the two end up byte-identical —
    # a stronger proof than checking one cell's probability, which the
    # other field's renormalization would perturb regardless.
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    scent_text = "Scent strongest to the north west."
    scent_focal = interpret_hint(scent_text, client.board)
    over_limit_text = " ".join(["south", "east"] * config.hint_word_limit)

    control = BeliefMap.uniform(client.board)
    control.update_from_scent_report(scent_focal, client.board)

    client._on_hint_received(over_limit_text, scent_text)

    assert client.belief_map._probabilities == control._probabilities


def test_on_hint_received_does_not_apply_an_over_limit_scent_report(config, tmp_path):
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    claim_text = "Near the south east side."
    claim_focal = interpret_hint(claim_text, client.board)
    over_limit_scent = " ".join(["north", "west"] * config.hint_word_limit)

    control = BeliefMap.uniform(client.board)
    control.update_from_hint(claim_focal, client.board)

    client._on_hint_received(claim_text, over_limit_scent)

    assert client.belief_map._probabilities == control._probabilities


def test_on_hint_received_applies_no_belief_update_for_a_no_signal_scent_report(config, tmp_path):
    # "A thief outside the sampling window produces an all-zero report":
    # once dominant_scent_direction reports genuinely no information
    # (is_no_scent_report), the receiver must skip update_from_scent_report
    # entirely — no signal reaches the belief map, rather than a weak wrong
    # one manufactured from interpret_hint's own north-west default.
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    claim_text = "Near the south east side."
    claim_focal = interpret_hint(claim_text, client.board)

    control = BeliefMap.uniform(client.board)
    control.update_from_hint(claim_focal, client.board)

    client._on_hint_received(claim_text, "No scent detected.")

    assert client.belief_map._probabilities == control._probabilities
