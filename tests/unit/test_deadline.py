"""Deadline tracker (rule 6): completes normally within the deadline, raises past it."""

from __future__ import annotations

import asyncio

import pytest

from cop.planner.deadline import DeadlineExceededError, await_with_deadline, now_and_deadline


async def _sleep_and_return(seconds: float, value: str) -> str:
    await asyncio.sleep(seconds)
    return value


def test_call_completing_within_the_deadline_returns_normally():
    result = asyncio.run(await_with_deadline(_sleep_and_return(0.01, "ack"), timeout_seconds=1.0))
    assert result == "ack"


def test_call_exceeding_the_deadline_raises_deadline_exceeded():
    # Test-only short timeout — never the real 30s default, so the suite stays fast.
    with pytest.raises(DeadlineExceededError, match="0.05s"):
        asyncio.run(await_with_deadline(_sleep_and_return(0.2, "too late"), timeout_seconds=0.05))


def test_now_and_deadline_places_the_deadline_exactly_timeout_seconds_after_sent_at():
    sent_at, deadline_at = now_and_deadline(timeout_seconds=30.0)
    assert deadline_at - sent_at == pytest.approx(30.0)


def test_now_and_deadline_sent_at_is_a_real_current_timestamp():
    import time

    before = time.time()
    sent_at, _ = now_and_deadline(timeout_seconds=1.0)
    after = time.time()
    assert before <= sent_at <= after
