"""std_v1/round_loop.py tests — the Thief always sends the first turn of
a sub-game; this repo (the Cop) only ever answers on even steps and
learns the outcome from the Thief's own `claim_response`/`win_claim`."""

from __future__ import annotations

import asyncio

from cop.std_v1.exchange import StdExchange
from cop.std_v1.round_loop import play_sub_game


class _FakeTurnHandler:
    """Always claims [9, 9] (out of the way) and never places a barrier —
    deterministic, so tests fully control the outcome via the Thief's own
    scripted replies."""

    def play_turn(self, thief_smell_grid, thief_hint_text):
        return {"move": "N", "hint": "", "barrier_placed": None, "capture_claim": [9, 9], "smell_grid": {}}


class _SpyConnection:
    def __init__(self):
        self.sent_messages: list[dict] = []

    async def call_tool(self, name, arguments):
        if name == "receive_turn":
            self.sent_messages.append(arguments["message"])

        class _Result:
            data = {"ok": True}

        return _Result()


def _thief_turn(step, commit="c", win_claim=None, claim_response=None):
    return {"step": step, "sender": "thief", "commit": commit, "win_claim": win_claim, "claim_response": claim_response}


def test_survival_when_the_thief_wins_on_its_very_first_turn():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn(_thief_turn(1, win_claim={"type": "survival"}))

    end_reason, records, peer_commits, _my_commits = asyncio.run(
        play_sub_game(_FakeTurnHandler(), _SpyConnection(), exchange, max_steps=1, turn_deadline_sec=1.0)
    )

    assert end_reason == "survival"
    assert records == []
    assert peer_commits == {1: "c"}


def test_capture_when_the_thief_confirms_the_claim():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn(_thief_turn(1, commit="c1"))
    exchange.record_turn(_thief_turn(3, commit="c3", claim_response={"claim": [9, 9], "caught": True}))

    end_reason, records, peer_commits, _my_commits = asyncio.run(
        play_sub_game(_FakeTurnHandler(), _SpyConnection(), exchange, max_steps=35, turn_deadline_sec=1.0)
    )

    assert end_reason == "capture"
    assert len(records) == 1
    assert peer_commits == {1: "c1", 3: "c3"}


def test_survival_when_the_thief_eventually_sends_win_claim():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn(_thief_turn(1, commit="c1"))
    exchange.record_turn(_thief_turn(3, commit="c3", claim_response={"claim": [9, 9], "caught": False}))
    exchange.record_turn(_thief_turn(5, commit="c5", win_claim={"type": "survival"}))

    end_reason, records, _peer_commits, _my_commits = asyncio.run(
        play_sub_game(_FakeTurnHandler(), _SpyConnection(), exchange, max_steps=5, turn_deadline_sec=1.0)
    )

    assert end_reason == "survival"
    assert len(records) == 2


def test_timeout_when_the_thief_never_sends_a_first_turn():
    exchange = StdExchange(poll_interval=0.01)

    end_reason, records, peer_commits, _my_commits = asyncio.run(
        play_sub_game(_FakeTurnHandler(), _SpyConnection(), exchange, max_steps=35, turn_deadline_sec=0.1)
    )

    assert end_reason == "timeout"
    assert records == []
    assert peer_commits == {}


def test_sent_turn_declares_a_capture_claim_on_every_reply():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn(_thief_turn(1, commit="c1"))
    exchange.record_turn(_thief_turn(3, commit="c3", win_claim={"type": "survival"}))
    connection = _SpyConnection()

    asyncio.run(play_sub_game(_FakeTurnHandler(), connection, exchange, max_steps=3, turn_deadline_sec=1.0))

    assert connection.sent_messages[0]["capture_claim"] == [9, 9]
    assert "move" not in connection.sent_messages[0]
