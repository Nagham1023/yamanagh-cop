"""One-method mixin, split out on its own purely for the 150-line house
cap — `orchestrator_peer.py` and `orchestrator_commit_reveal.py` were both
already at/near the cap when this landed. `CommitRevealMixin`
(`orchestrator_commit_reveal.py`) is the only caller.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from .planner.deadline import await_with_deadline
from .planner.retry import retry_on_connection_failure
from .tools.peer_connection import is_connect_only_failure

T = TypeVar("T")


class ConnectRetryMixin:
    async def _call_with_connect_retry(
        self, call: Callable[[], Awaitable[T]], *, timeout_seconds: float
    ) -> T:
        """Bounded retry restricted to `is_connect_only_failure`'s
        provably-safe case — the request was never transmitted, so
        retrying cannot double-apply it. `CommitRevealMixin`'s per-turn
        calls (send_commit/send_reveal/send_barrier_declaration) are NOT
        idempotent in general (`mcp_client_prd6.py`'s own docstring), so
        anything past this narrow case must still surface with zero
        retry — unlike `_pull_scent_map_with_retry`
        (`orchestrator_peer.py`), a pure read that can retry on any
        connection failure. Found live: a bare `ConnectError` on
        `send_commit` — from the persistent `PeerConnection`'s own pooled
        transport failing to re-establish, not the first handshake —
        ended a real 27-round match one step short of completing, even
        though nothing had actually been sent. Reuses the same
        `scent_map_retry_*` config fields as the scent-map/final-reveal
        retries (`private_config.py`) — one shared retry budget, not a
        fourth set of numbers."""
        return await await_with_deadline(
            retry_on_connection_failure(
                call,
                attempts=self.private_config.scent_map_retry_attempts,
                delay_seconds=self.private_config.scent_map_retry_delay_seconds,
                on_retry=lambda attempt, exc: self.trace.log(
                    "commit_reveal_send_retrying", attempt=attempt, reason=str(exc)
                ),
                retryable=is_connect_only_failure,
            ),
            timeout_seconds=timeout_seconds,
        )
