"""Watchdog (rule 7): monitors the process, extracts data on crash.

Rule 7's own sanction is "game crash **and loss of the official record**" —
`persist_state`/`controlled_shutdown` exist to prevent exactly that. Mirrors
the book's own `watchdog_check` sketch (Ch.8 §8.4); threshold sourced from
`config.watchdog_threshold_seconds` (invariant I6), never a literal.

`persist_state`/`controlled_shutdown`/`clock` are injected rather than
hardcoded so a test can trigger a "stale heartbeat" deterministically
instead of actually sleeping past the real threshold — and so this module
has no direct `Trace` dependency. The Orchestrator is what injects a real
`persist_state` that calls `Trace.log(...)`, which is the actual
integration point, not an import here.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class Watchdog:
    def __init__(
        self,
        threshold_seconds: float,
        persist_state: Callable[[], None],
        controlled_shutdown: Callable[[], None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold_seconds = threshold_seconds
        self._persist_state = persist_state
        self._controlled_shutdown = controlled_shutdown
        self._clock = clock
        self._last_heartbeat = clock()

    def heartbeat(self) -> None:
        """Record that the main loop is still alive."""
        self._last_heartbeat = self._clock()

    def check(self) -> str:
        """Return `"ALIVE"` if the last heartbeat is recent; otherwise trigger recovery."""
        elapsed = self._clock() - self._last_heartbeat
        if elapsed > self._threshold_seconds:
            self._persist_state()
            self._controlled_shutdown()
            return "SHUTDOWN"
        return "ALIVE"
