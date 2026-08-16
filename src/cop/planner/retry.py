"""Bounded retry for genuinely idempotent peer calls only (PRD 5/10) — a
tunnel blip lasting under the retry budget must not cost the match, but
this must never be reached for a call that could double-apply on the
peer's own side (commit/reveal/capture keep their existing, deliberate
zero-retry policy — `mcp_client_prd6.py`'s docstring has that reasoning).
Shared between `orchestrator_peer.py`'s scent-map pull and
`orchestrator_peer_audit.py`'s Final Reveal send, both confirmed
idempotent on the receiving side (a pure read; a pure overwrite via
`PeerTrace.record_final_reveal`'s own `setdefault`) once a real
cross-machine match showed a sub-second-to-~1s tunnel drop costing a
whole game via the scent-map call alone.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_on_connection_failure(
    call: Callable[[], Awaitable[T]],
    *,
    attempts: int,
    delay_seconds: float,
    on_retry: Callable[[int, Exception], None] | None = None,
    retryable: Callable[[Exception], bool] = lambda exc: True,
) -> T:
    """Calls `call()` up to `attempts` times, waiting `delay_seconds`
    between failures. `retryable` lets a caller exclude a non-connection
    exception it already handles specially (e.g. malformed-data
    `ValueError`, which retrying can never fix) — such an exception
    re-raises immediately, on the first attempt, same as no retry at all."""
    for attempt in range(attempts):
        try:
            return await call()
        except Exception as exc:
            if not retryable(exc) or attempt + 1 >= attempts:
                raise
            if on_retry is not None:
                on_retry(attempt + 1, exc)
            await asyncio.sleep(delay_seconds)
    raise AssertionError("unreachable: attempts must be >= 1")
