"""Rule 28: the token-bucket rate limiter, ch. 9.3.2's own formula
(`tokens <- min(C, tokens + r*dt)`, `allow() <=> tokens >= 1`). Deterministic
via monkeypatching `time.monotonic`, not real sleeps — same discipline as
this repo's own watchdog tests (force staleness directly, don't wait for it).
"""

from __future__ import annotations

import pytest

import cop.policy.token_bucket as token_bucket_module
from cop.policy.token_bucket import TokenBucket


def _freeze_clock(monkeypatch, start: float = 0.0):
    clock = {"now": start}
    monkeypatch.setattr(token_bucket_module.time, "monotonic", lambda: clock["now"])
    return clock


def test_fresh_bucket_allows_capacity_calls_then_blocks(monkeypatch):
    _freeze_clock(monkeypatch)
    bucket = TokenBucket(capacity=3, refill_rate=1.0)

    assert bucket.allow() is True
    assert bucket.allow() is True
    assert bucket.allow() is True
    assert bucket.allow() is False


def test_refill_after_enough_elapsed_time_allows_one_more_call(monkeypatch):
    clock = _freeze_clock(monkeypatch)
    bucket = TokenBucket(capacity=1, refill_rate=0.5)  # 1 token per 2 seconds

    assert bucket.allow() is True
    assert bucket.allow() is False

    clock["now"] += 2.0  # exactly one token's worth of refill
    assert bucket.allow() is True


def test_refill_clamps_at_capacity_not_unbounded(monkeypatch):
    clock = _freeze_clock(monkeypatch)
    bucket = TokenBucket(capacity=2, refill_rate=1.0)

    bucket.allow()
    bucket.allow()
    clock["now"] += 1000.0  # a very long wait

    # Clamped at capacity=2, not accumulated to ~1000 tokens.
    assert bucket.allow() is True
    assert bucket.allow() is True
    assert bucket.allow() is False


def test_allow_rejects_a_non_positive_cost():
    bucket = TokenBucket(capacity=5, refill_rate=1.0)
    with pytest.raises(ValueError):
        bucket.allow(cost=0)
    with pytest.raises(ValueError):
        bucket.allow(cost=-1)
