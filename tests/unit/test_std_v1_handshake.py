"""std_v1/handshake.py tests — exercised against a real StdExchange on
"the other side" so this is a genuine mutual exchange, not just one half
in isolation. Async (`negotiate_sub_game` awaits `send_negotiate`), so
every test drives it via `asyncio.run`, matching this repo's own
established async-test pattern (`test_cli_peer.py`)."""

from __future__ import annotations

import asyncio

import pytest

from cop.planner.deadline import DeadlineExceededError
from cop.std_v1.crypto import commit_of, derive_game_uid, fresh_nonce
from cop.std_v1.exchange import StdExchange
from cop.std_v1.handshake import build_offer, negotiate_sub_game, validate_offer
from cop.std_v1.terms import load_terms

TERMS = load_terms()


class _PeerConnection:
    """Delivers calls directly into the peer's own StdExchange, standing
    in for a real MCP round trip."""

    def __init__(self, peer_exchange: StdExchange):
        self._peer_exchange = peer_exchange

    async def call_tool(self, name, arguments):
        assert name == "negotiate"
        self._peer_exchange.record_offer(arguments["message"])

        class _Result:
            data = {"ok": True}

        return _Result()


def test_negotiate_sub_game_returns_the_peers_validated_offer():
    my_exchange = StdExchange(poll_interval=0.01)
    their_exchange = StdExchange(poll_interval=0.01)
    my_connection = _PeerConnection(their_exchange)

    game_uid = derive_game_uid(TERMS, "dev-team", "thief-team")
    their_offer = build_offer(TERMS, "thief-team", "thief", 1, {"group_id": "thief-team"}, game_uid, fresh_nonce())
    my_exchange.record_offer(their_offer)

    result = asyncio.run(negotiate_sub_game(
        my_connection, my_exchange, TERMS, "dev-team", "thief-team", "police", 1,
        {"group_id": "dev-team"}, resend_interval_sec=0.05, ceiling_sec=2.0,
    ))

    assert result == their_offer
    sent = their_exchange.wait_for_offer(1, timeout=1.0)
    assert sent["group_id"] == "dev-team"
    assert sent["role"] == "police"


def test_negotiate_sub_game_times_out_when_the_peer_never_answers():
    my_exchange = StdExchange(poll_interval=0.01)
    their_exchange = StdExchange(poll_interval=0.01)
    connection = _PeerConnection(their_exchange)

    with pytest.raises(DeadlineExceededError):
        asyncio.run(negotiate_sub_game(
            connection, my_exchange, TERMS, "dev-team", "thief-team", "police", 1,
            {"group_id": "dev-team"}, resend_interval_sec=0.05, ceiling_sec=0.2,
        ))


def test_negotiate_sub_game_rejects_a_mismatched_game_uid():
    my_exchange = StdExchange(poll_interval=0.01)
    their_exchange = StdExchange(poll_interval=0.01)
    connection = _PeerConnection(their_exchange)

    bad_offer = build_offer(TERMS, "thief-team", "thief", 1, {}, "not-the-real-uid", fresh_nonce())
    my_exchange.record_offer(bad_offer)

    with pytest.raises(ValueError, match="game_uid"):
        asyncio.run(negotiate_sub_game(
            connection, my_exchange, TERMS, "dev-team", "thief-team", "police", 1,
            {"group_id": "dev-team"}, resend_interval_sec=0.05, ceiling_sec=2.0,
        ))


def test_validate_offer_rejects_terms_that_differ():
    offer = build_offer({**TERMS, "setting": "Tampered"}, "thief-team", "thief", 1, {}, "uid", fresh_nonce())
    with pytest.raises(ValueError, match="differ"):
        validate_offer(offer, TERMS)


def test_validate_offer_rejects_a_bad_signature():
    offer = build_offer(TERMS, "thief-team", "thief", 1, {}, "uid", fresh_nonce())
    offer["signature"] = "0" * 64
    with pytest.raises(ValueError, match="signature"):
        validate_offer(offer, TERMS)


def test_validate_offer_rejects_a_missing_group_id():
    offer = build_offer(TERMS, "", "thief", 1, {}, "uid", fresh_nonce())
    offer["group_id"] = ""
    with pytest.raises(ValueError, match="group_id"):
        validate_offer(offer, TERMS)


def test_validate_offer_accepts_a_well_formed_matching_offer():
    nonce = fresh_nonce()
    offer = build_offer(TERMS, "thief-team", "thief", 1, {}, "uid", nonce)
    validate_offer(offer, TERMS)  # must not raise


def test_build_offer_signature_matches_commit_of():
    nonce = fresh_nonce()
    offer = build_offer(TERMS, "thief-team", "thief", 1, {}, "uid", nonce)
    assert offer["signature"] == commit_of(TERMS, nonce)
