"""std_v1/exchange.py tests — the cross-thread mailbox, exercised with
real threads so the lock actually matters, not just single-threaded calls."""

from __future__ import annotations

import threading
import time

import pytest

from cop.planner.deadline import DeadlineExceededError
from cop.std_v1.exchange import StdExchange


def test_wait_for_turn_returns_once_recorded():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn({"step": 3, "sender": "thief"})
    assert exchange.wait_for_turn(3, timeout=1.0)["sender"] == "thief"


def test_wait_for_turn_times_out_when_never_recorded():
    exchange = StdExchange(poll_interval=0.01)
    with pytest.raises(DeadlineExceededError):
        exchange.wait_for_turn(3, timeout=0.1)


def test_wait_for_turn_unblocks_from_a_different_thread():
    exchange = StdExchange(poll_interval=0.01)

    def _writer():
        time.sleep(0.05)
        exchange.record_turn({"step": 5, "sender": "thief"})

    threading.Thread(target=_writer).start()
    assert exchange.wait_for_turn(5, timeout=2.0)["step"] == 5


def test_offer_accepted_via_none_keyed_bucket():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_offer({"group_id": "dev-team"})  # no sub_game_number at all
    assert exchange.wait_for_offer(1, timeout=1.0)["group_id"] == "dev-team"


def test_offer_exact_key_wins_over_none_bucket_when_both_present():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_offer({"sub_game_number": None, "group_id": "generic"})
    exchange.record_offer({"sub_game_number": 2, "group_id": "specific"})
    assert exchange.wait_for_offer(2, timeout=1.0)["group_id"] == "specific"


def test_wait_for_consensus_reads_the_none_keyed_audit_bucket():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_audit({"result_claim": "series_consensus", "consensus_sha": "a" * 64})
    assert exchange.wait_for_consensus(timeout=1.0)["consensus_sha"] == "a" * 64


def test_latest_control_returns_none_when_empty():
    exchange = StdExchange(poll_interval=0.01)
    assert exchange.latest_control() is None


def test_latest_control_returns_the_most_recent_message():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_control({"type": "ping", "seq": 1})
    exchange.record_control({"type": "ping", "seq": 2})
    assert exchange.latest_control()["seq"] == 2


def test_reset_turns_clears_a_leftover_step_from_a_prior_sub_game():
    # Regression: found via a real two-repo match against thief-peer --
    # step numbers restart at 1 every sub-game, so without reset_turns()
    # a stale step-1 message from sub-game 1 gets handed back instantly
    # as sub-game 2's own, and every later step audits as tampered.
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn({"step": 1, "sender": "thief", "sub_game": "stale"})

    exchange.reset_turns()

    with pytest.raises(DeadlineExceededError):
        exchange.wait_for_turn(1, timeout=0.1)


def test_reset_turns_does_not_touch_offers_or_audits():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_offer({"sub_game_number": 1, "group_id": "thief-team"})
    exchange.record_audit({"sub_game_number": 1, "result_claim": "capture"})

    exchange.reset_turns()

    assert exchange.wait_for_offer(1, timeout=1.0)["group_id"] == "thief-team"
    assert exchange.wait_for_audit(1, timeout=1.0)["result_claim"] == "capture"
