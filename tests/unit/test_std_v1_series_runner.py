"""std_v1/series_runner.py tests — a scripted fake "thief-team" peer
answering inline inside its own `call_tool`, driving a real two-sub-game
series end to end through negotiate -> round_loop -> audit -> consensus.
Section 6/10 [MATCH] role alternation means sub-game 1 (odd) is our
natural Police role and sub-game 2 (even) is our alternated Thief role
-- the fake peer is therefore symmetric too: it plays Thief (its own
natural role, complementary to ours) on sub-game 1 and Police on
sub-game 2, always evading/missing so every sub-game ends in survival."""

from __future__ import annotations

import asyncio

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.memory.scent import ScentField
from cop.reasoning.state import GameState
from cop.std_v1.audit import build_audit_envelope, build_consensus_envelope, build_consensus_object
from cop.std_v1.crypto import consensus_digest, derive_game_id, derive_game_uid, fresh_nonce
from cop.std_v1.exchange import StdExchange
from cop.std_v1.handshake import build_offer
from cop.std_v1.roles import opposite_role, role_for_sub_game
from cop.std_v1.sealing import build_audit_record, build_turn_payload, seal_turn
from cop.std_v1.series_runner import NATURAL_ROLE, _row_for, play_series
from cop.std_v1.terms import load_terms

MY_GROUP = "dev-team"
THEIR_GROUP = "thief-team"
TERMS = {**load_terms(), "max_steps": 3, "num_games": 2}


class _Result:
    def __init__(self, data):
        self.data = data


class _FakeTurnHandler:
    def play_turn(self, thief_smell_grid, thief_hint_text):
        return {"move": "N", "hint": "", "barrier_placed": None, "capture_claim": [6, 6], "smell_grid": {}}


def _thief_components_factory():
    board = Board(size=TERMS["board_size"])
    barriers = BarrierSet(quota=TERMS["barriers_max"])
    state = GameState(
        own_pos=Position(*TERMS["thief_start"]), target_pos=Position(*TERMS["cop_start"]), barriers=barriers
    )
    scent_field = ScentField(
        source_strength=TERMS["emit_intensity"], decay_rate=TERMS["decay_per_step"], window_size=TERMS["smell_grid_size"]
    )
    return board, state, scent_field


def _expected_digest(num_games: int) -> str:
    rows = [
        _row_for(n, role_for_sub_game(NATURAL_ROLE, n), "survival", False, MY_GROUP, THEIR_GROUP)
        for n in range(1, num_games + 1)
    ]
    game_id = derive_game_id(MY_GROUP, THEIR_GROUP)
    game_uid = derive_game_uid(TERMS, MY_GROUP, THEIR_GROUP)
    return consensus_digest(build_consensus_object(game_id, game_uid, rows))


class _FakePeerConnection:
    """A scripted "thief-team" opponent that alternates roles the same
    way we do (complementary every sub-game): plays Thief on our Police
    sub-games (never confirms a capture, so it survives) and Police on
    our Thief sub-games (always misses, so we survive)."""

    def __init__(self, my_exchange: StdExchange, peer_digest=None, peer_result_claim=None):
        self._exchange = my_exchange
        self._game_uid = derive_game_uid(TERMS, MY_GROUP, THEIR_GROUP)
        self._peer_digest = peer_digest
        self._peer_result_claim = peer_result_claim
        self._peer_records: dict[int, list[dict]] = {}
        self._current_sub_game = 0
        self._peer_role = "thief"

    async def call_tool(self, name, arguments):
        if name == "negotiate":
            self._handle_negotiate(arguments["message"])
        elif name == "receive_turn":
            self._handle_turn(arguments["message"])
        elif name == "submit_audit":
            self._handle_audit(arguments["payload"])
        return _Result({"ok": True})

    def _handle_negotiate(self, offer):
        sub_game_number = offer["sub_game_number"]
        self._peer_role = opposite_role(offer["role"])
        their_offer = build_offer(
            TERMS, THEIR_GROUP, self._peer_role, sub_game_number, {"group_id": THEIR_GROUP},
            self._game_uid, fresh_nonce(),
        )
        self._exchange.record_offer(their_offer)
        self._current_sub_game = sub_game_number
        self._peer_records[sub_game_number] = []
        if self._peer_role == "thief":
            # The Thief always sends the first turn of a sub-game.
            self._send_thief_turn(1, win_claim=None)

    def _handle_turn(self, message):
        if message["sender"] == "police":
            next_step = message["step"] + 1
            win_claim = {"type": "survival"} if next_step >= TERMS["max_steps"] else None
            self._send_thief_turn(next_step, win_claim)
        else:  # message["sender"] == "thief" -- we're the Thief, peer replies as Police
            if message["step"] >= TERMS["max_steps"]:
                return  # the win-claiming final turn needs no reply
            self._send_police_turn(message["step"] + 1)

    def _send_thief_turn(self, step, win_claim):
        payload = build_turn_payload(step=step, sender="thief", move="STAY", hint="", smell_grid={}, win_claim=win_claim)
        sealed = seal_turn(payload)
        record = build_audit_record(payload, sealed["nonce"])
        self._peer_records[self._current_sub_game].append(record)
        self._exchange.record_turn({**payload, "commit": sealed["commit"]})

    def _send_police_turn(self, step):
        payload = build_turn_payload(
            step=step, sender="police", move="STAY", hint="", smell_grid={}, capture_claim=[6, 6]
        )
        sealed = seal_turn(payload)
        record = build_audit_record(payload, sealed["nonce"])
        self._peer_records[self._current_sub_game].append(record)
        self._exchange.record_turn(
            {**payload, "commit": sealed["commit"], "capture_claim": [6, 6], "barrier_placed": None}
        )

    def _handle_audit(self, payload):
        if payload.get("result_claim") == "series_consensus" and "sub_game_number" not in payload:
            digest = self._peer_digest if self._peer_digest is not None else _expected_digest(TERMS["num_games"])
            self._exchange.record_audit(build_consensus_envelope(self._peer_role, digest))
            return
        sub_game_number = payload["sub_game_number"]
        result_claim = self._peer_result_claim if self._peer_result_claim is not None else "survival"
        envelope = build_audit_envelope(
            self._peer_role, self._peer_records[sub_game_number], result_claim, sub_game_number
        )
        self._exchange.record_audit(envelope)


def test_play_series_happy_path_reaches_agreement():
    exchange = StdExchange(poll_interval=0.01)
    connection = _FakePeerConnection(exchange)

    result = asyncio.run(play_series(
        connection, exchange, TERMS, MY_GROUP, THEIR_GROUP, {"group_id": MY_GROUP},
        lambda: _FakeTurnHandler(), _thief_components_factory,
        turn_deadline_sec=2.0, resend_interval_sec=0.05, negotiate_ceiling_sec=2.0, audit_ceiling_sec=2.0,
    ))

    assert result["agreed"] is True
    rows = result["consensus_object"]["sub_games"]
    assert len(rows) == 2
    assert all(row["result"] == "survival" for row in rows)
    # sub-game 1: we play our natural Police role; the peer (Thief) survives -> the peer wins.
    assert rows[0]["roles"][MY_GROUP] == "police"
    assert rows[0]["winner_group"] == THEIR_GROUP
    # sub-game 2: role alternates -- we play Thief and survive -> we win, not the peer.
    assert rows[1]["roles"][MY_GROUP] == "thief"
    assert rows[1]["winner_group"] == MY_GROUP


def test_play_series_flags_disagreement_when_peer_digest_differs():
    exchange = StdExchange(poll_interval=0.01)
    connection = _FakePeerConnection(exchange, peer_digest="0" * 64)

    result = asyncio.run(play_series(
        connection, exchange, TERMS, MY_GROUP, THEIR_GROUP, {"group_id": MY_GROUP},
        lambda: _FakeTurnHandler(), _thief_components_factory,
        turn_deadline_sec=2.0, resend_interval_sec=0.05, negotiate_ceiling_sec=2.0, audit_ceiling_sec=2.0,
    ))

    assert result["agreed"] is False
    assert result["peer_consensus_sha"] == "0" * 64


def test_play_series_flags_disagreement_when_peer_result_claim_differs():
    exchange = StdExchange(poll_interval=0.01)
    connection = _FakePeerConnection(exchange, peer_result_claim="capture")

    result = asyncio.run(play_series(
        connection, exchange, TERMS, MY_GROUP, THEIR_GROUP, {"group_id": MY_GROUP},
        lambda: _FakeTurnHandler(), _thief_components_factory,
        turn_deadline_sec=2.0, resend_interval_sec=0.05, negotiate_ceiling_sec=2.0, audit_ceiling_sec=2.0,
    ))

    assert result["agreed"] is False


def test_row_for_uses_the_spec_score_table_and_flips_with_role():
    capture_row = _row_for(1, "police", "capture", False, MY_GROUP, THEIR_GROUP)
    assert capture_row["score"] == {MY_GROUP: 20, THEIR_GROUP: 5}
    assert capture_row["winner_group"] == MY_GROUP

    survival_row = _row_for(2, "thief", "survival", False, MY_GROUP, THEIR_GROUP)
    assert survival_row["score"] == {MY_GROUP: 10, THEIR_GROUP: 5}
    assert survival_row["winner_group"] == MY_GROUP

    tamper_row = _row_for(3, "police", "capture", True, MY_GROUP, THEIR_GROUP)
    assert tamper_row["result"] == "tamper_forfeit"
    assert tamper_row["score"] == {MY_GROUP: 0, THEIR_GROUP: 0}
    assert tamper_row["winner_group"] is None
