"""`ApiGatekeeper` — the facade `software_submission_guidelines-V3.pdf` §5.1
requires (`execute(api_call, *args, **kwargs)`, `get_queue_status()`),
composing ch. 9.3.1's own three accumulating protections in the book's own
order (Fig. 13): Quota Manager → Token Bucket → DOS Detector → the wrapped
call. Fail-fast at the first *gate* that rejects, per the book's own "כשל
מהיר" (fail fast) principle (p.90) — a gate rejection raises immediately,
never queues (Fig. 13's own diagram branches straight to
`Rejected`/`Blocked`/`LOCKED`, never to a holding queue); `get_queue_status()`
therefore reports *counts*, not a literal pending queue, and `queue_depth`
stays `0` by design.

The guide's own `execute()` description separately requires "retry on
transient failures" — that's `api_call` itself failing *after* every gate
approved it (e.g. a real Gmail 429), not a gate rejection. Each retry is a
genuinely new outgoing attempt, so it re-enters the gates rather than
bypassing them (rule 28's own "respect a 429, never retry blindly" —
`retry_backoff_sec`/`max_retries`, Table 19, both read from config, never
hardcoded).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from ..shared.config import GameConfig
from .dos_detector import DosDetector
from .quota_manager import QuotaManager
from .token_bucket import TokenBucket

_T = TypeVar("_T")

# Not a Table 19 field (Design Question 5's own "not a book-mandated number"
# label) — this repo's own daily ceiling, generous enough not to bite a real
# 6-sub-game series's worth of reports, conservative enough to still be a
# real "last line of defense."
_DEFAULT_DAILY_CEILING = 500


class GatekeeperRejectionError(Exception):
    """Raised by `execute()` when a gate rejects the call outright — carries
    which gate, so a caller (or a test) can distinguish quota exhaustion
    from a rate-limit hit from a DOS lock without parsing a message string."""

    def __init__(self, gate: str, reason: str) -> None:
        self.gate = gate
        super().__init__(f"{gate}: {reason}")


@dataclass
class QueueStatus:
    approved: int = 0
    rejected_by_quota_manager: int = 0
    rejected_by_token_bucket: int = 0
    rejected_by_dos_detector: int = 0
    retries: int = 0
    queue_depth: int = field(default=0)  # always 0 — fail-fast, never queued (see module docstring)


class ApiGatekeeper:
    def __init__(self, config: GameConfig, daily_ceiling: int = _DEFAULT_DAILY_CEILING) -> None:
        self._quota = QuotaManager(daily_ceiling=daily_ceiling)
        self._bucket = TokenBucket(
            capacity=config.rate_limit_requests_per_minute,
            refill_rate=config.rate_limit_requests_per_minute / 60.0,
        )
        self._dos = DosDetector()
        self._max_retries = config.rate_limit_max_retries
        self._retry_backoff_seconds = config.rate_limit_retry_backoff_seconds
        self._status = QueueStatus()

    def _pass_gates(self) -> None:
        """Raises `GatekeeperRejectionError` on the first gate that rejects;
        returns normally once all three approve. Never retried internally —
        a gate rejection means "not now," not "transient," so the caller
        (or the outer retry loop's *next attempt*) re-checks fresh state."""
        if not self._quota.allow():
            self._status.rejected_by_quota_manager += 1
            raise GatekeeperRejectionError("quota_manager", "daily ceiling reached")
        if not self._bucket.allow():
            self._status.rejected_by_token_bucket += 1
            raise GatekeeperRejectionError("token_bucket", "rate limit exceeded")
        if self._dos.is_locked():
            self._status.rejected_by_dos_detector += 1
            raise GatekeeperRejectionError("dos_detector", "locked — manual reset required")

    def execute(self, api_call: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
        """Runs Quota Manager → Token Bucket → DOS Detector (ch. 9.3.1, Fig. 13);
        only calls `api_call` if every gate approves. If `api_call` itself
        raises, retries up to `max_retries` times with `retry_backoff_sec`
        between attempts — each attempt re-enters the gates."""
        for attempt in range(self._max_retries + 1):
            self._pass_gates()
            self._dos.record_attempt()
            try:
                result = api_call(*args, **kwargs)
            except Exception:
                if attempt < self._max_retries:
                    self._status.retries += 1
                    time.sleep(self._retry_backoff_seconds)
                    continue
                raise
            else:
                self._dos.record_success()
                self._status.approved += 1
                return result

    def get_queue_status(self) -> QueueStatus:
        return self._status
