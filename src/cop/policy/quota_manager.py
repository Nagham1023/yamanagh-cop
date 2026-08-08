"""The daily safety-ceiling gate — ch. 9.3.1's first Gatekeeper layer ("last
line of defense," the book's own framing): counts requests sent today,
blocks once a configured daily cap is hit. Resets at UTC calendar-day
boundaries, not per-process-start — a restarted process must not silently
reset a count that's supposed to track a whole day's real usage.
"""

from __future__ import annotations

import datetime


def _today() -> datetime.date:
    return datetime.datetime.now(datetime.UTC).date()


class QuotaManager:
    def __init__(self, daily_ceiling: int) -> None:
        self.daily_ceiling = daily_ceiling
        self._count = 0
        self._day = _today()

    def _roll_over_if_new_day(self) -> None:
        today = _today()
        if today != self._day:
            self._day = today
            self._count = 0

    def allow(self) -> bool:
        """Return `True` and record the attempt if under today's ceiling,
        else `False` — the "last line of defense" (ch. 9.3.1): even a
        perfectly rate-limited sender still stops here once the day's own
        cap is spent."""
        self._roll_over_if_new_day()
        if self._count >= self.daily_ceiling:
            return False
        self._count += 1
        return True

    @property
    def count_today(self) -> int:
        self._roll_over_if_new_day()
        return self._count
