"""Deadline tracker (rule 6): wraps a wait on the opponent with a timeout.

The timeout is always `config.response_timeout_seconds` — never a literal
(invariant I6). Expiry raises `DeadlineExceededError`, a controlled, expected
exception the Orchestrator catches to drive the state machine to
`TECHNICAL_LOSS` — not an uncaught exception that crashes the process.

This module has no `Trace` dependency on purpose: it stays a pure function,
testable with nothing but `asyncio`. The Orchestrator is what catches
`DeadlineExceededError` and writes the "intact log" the milestone requires —
that's the actual integration point, not an import here.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")


class DeadlineExceededError(Exception):
    """Raised when a wait on the opponent exceeds `response_timeout_seconds`."""


async def await_with_deadline(coro: Awaitable[T], timeout_seconds: float) -> T:
    """Await `coro`, raising `DeadlineExceededError` if it doesn't finish in time."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except TimeoutError as exc:
        raise DeadlineExceededError(f"opponent did not respond within {timeout_seconds}s") from exc


def now_and_deadline(timeout_seconds: float) -> tuple[float, float]:
    """PRD 15 (ch. 8.4): the wire-level `(sent_at, deadline_at)` pair a
    request carries alongside `Hcommit`/`move`/etc. — one shared
    computation rather than repeating `time.time() + timeout_seconds` at
    every `send_*` call site (I6). This is purely observational once it
    crosses the wire (rule 9: a peer's own declared timing is untrusted) —
    the receiver logs it, never lets it shorten/extend its own
    `await_with_deadline` bound, which stays the sole authoritative timeout."""
    sent_at = time.time()
    return sent_at, sent_at + timeout_seconds
