"""The book's own token-bucket rate limiter (ch. 9.3.2, p.77's worked code),
shape unchanged: `tokens ← min(C, tokens + r·Δt)`, `allow() ⇐⇒ tokens ≥ 1`.
Rate-tokens only — entirely unrelated to LLM tokens or OAuth tokens
(`PRD-7-reporting-shell.md`'s Design Question 5a: three kinds of "token" in
this project, never to be confused).

`capacity`/`refill_rate` are constructor parameters, not hardcoded (rule I6)
— the caller (`policy/gatekeeper.py`) sources them from the negotiated
config's `rate_limiter_gatekeeper` block.
"""

from __future__ import annotations

import time


class TokenBucket:
    def __init__(self, capacity: float, refill_rate: float) -> None:
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self._last = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self._last = now

    def allow(self, cost: float = 1.0) -> bool:
        """Return `True` and spend a token if one is available, else `False`
        — the caller backs off/retries later, this never blocks."""
        if cost <= 0:
            raise ValueError(f"cost must be positive, got {cost!r}")
        self._refill()
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False
