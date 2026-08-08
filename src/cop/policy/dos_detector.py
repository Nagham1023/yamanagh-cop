"""Statistical anomaly detector on the *sending pattern itself* (ch. 9.3.1's
third Gatekeeper layer) — catches a bug or infinite loop in this repo's own
code, not a hostile peer, and locks the whole channel rather than let a
runaway loop get the account suspended by the provider. The book names the
pattern (a circuit-breaker/backpressure mechanism) without a specific
statistic — `_CONSECUTIVE_THRESHOLD`/`_WINDOW_SECONDS` below are this repo's
own choice, not a book-mandated number (same "book gives the concept, not
the number" label used for the belief-map reliability coefficient).
"""

from __future__ import annotations

import time

_CONSECUTIVE_THRESHOLD = 5
_WINDOW_SECONDS = 10.0


class DosDetector:
    def __init__(
        self,
        consecutive_threshold: int = _CONSECUTIVE_THRESHOLD,
        window_seconds: float = _WINDOW_SECONDS,
    ) -> None:
        self.consecutive_threshold = consecutive_threshold
        self.window_seconds = window_seconds
        self._streak = 0
        self._streak_started_at: float | None = None
        self._locked = False

    def record_attempt(self) -> None:
        """A send was attempted (approved by the earlier gates). Consecutive
        attempts with no intervening `record_success()`, all within
        `window_seconds` of the streak's own start, trip `LOCKED` at
        `consecutive_threshold` — a healthy but bursty sender resets the
        streak via `record_success()` long before that; a stuck loop never
        does."""
        if self._locked:
            return
        now = time.monotonic()
        if self._streak_started_at is None or (now - self._streak_started_at) > self.window_seconds:
            self._streak_started_at = now
            self._streak = 1
        else:
            self._streak += 1
        if self._streak >= self.consecutive_threshold:
            self._locked = True

    def record_success(self) -> None:
        """A send actually succeeded — the streak that matters is
        consecutive *unanswered* attempts, so a genuine success clears it."""
        self._streak = 0
        self._streak_started_at = None

    def is_locked(self) -> bool:
        return self._locked

    def reset(self) -> None:
        """Manual reset only — matching the book's own circuit-breaker
        framing. Nothing in this class clears `LOCKED` on its own; a human
        decides the underlying bug is fixed."""
        self._locked = False
        self._streak = 0
        self._streak_started_at = None
