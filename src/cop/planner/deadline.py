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
