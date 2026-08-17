"""Outbound calls to a std_v1 peer, matching the spec's exact tool and
argument names (Section 7): `negotiate(message)`, `receive_turn(message)`,
`submit_audit(payload)`, `receive_control(message)` — note `submit_audit`
alone takes `payload`, not `message`. Async, through a `PeerConnection`
(`tools/peer_connection.py`) — the same persistent-connection object the
native protocol's own client calls already use, so a std_v1 match gets
the same "one connection reused for the whole match" robustness a real
tunnel needs (`peer_connection.py`'s own docstring has the full story).

Every call here is retryable on a connect-only failure: Section 7
requires a receive tool to validate lightly, enqueue, and return `{"ok":
true}` immediately — there is no non-idempotent state mutation happening
synchronously inside the call itself, unlike this repo's native
commit/reveal calls (`orchestrator_connect_retry.py`'s own docstring has
that distinction). Retrying here matters in practice, not just in theory:
each sub-game's own negotiate/audit resend loop (`handshake.py`/
`audit.py`) already re-sends on a timer, but a bare `PeerConnection`
raises straight through a transient "peer not listening yet" instead of
looping past it (confirmed live — the very first negotiate attempt of a
real match routinely beats the peer's own server startup by a beat),
which would otherwise crash the whole match on nothing worse than a race
at startup.
"""

from __future__ import annotations

from typing import Any

from ..planner.retry import retry_on_connection_failure
from ..tools.peer_connection import PeerConnection, is_connect_only_failure

# I6: these two used to be fixed module constants — the exact "fourth set
# of numbers" orchestrator_connect_retry.py's own docstring warns against.
# Every real call site now threads PrivateConfig.scent_map_retry_attempts/
# scent_map_retry_delay_seconds down to here (the same shared retry budget
# the native protocol's scent-map/final-reveal retries already use); these
# defaults exist only so tests can call a send_* function directly without
# wiring a full PrivateConfig through.
_DEFAULT_RETRY_ATTEMPTS = 3
_DEFAULT_RETRY_DELAY_SECONDS = 1.0


async def _call_with_connect_retry(
    connection: PeerConnection, tool_name: str, arguments: dict,
    retry_attempts: int, retry_delay_seconds: float,
) -> Any:
    result = await retry_on_connection_failure(
        lambda: connection.call_tool(tool_name, arguments),
        attempts=retry_attempts,
        delay_seconds=retry_delay_seconds,
        retryable=is_connect_only_failure,
    )
    return result.data


async def send_negotiate(
    connection: PeerConnection, offer: dict,
    retry_attempts: int = _DEFAULT_RETRY_ATTEMPTS, retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS,
) -> Any:
    """Calls the peer's `negotiate` tool with this side's own offer."""
    return await _call_with_connect_retry(
        connection, "negotiate", {"message": offer}, retry_attempts, retry_delay_seconds
    )


async def send_turn(
    connection: PeerConnection, message: dict,
    retry_attempts: int = _DEFAULT_RETRY_ATTEMPTS, retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS,
) -> Any:
    """Calls the peer's `receive_turn` tool with one sealed turn message."""
    return await _call_with_connect_retry(
        connection, "receive_turn", {"message": message}, retry_attempts, retry_delay_seconds
    )


async def send_audit(
    connection: PeerConnection, envelope: dict,
    retry_attempts: int = _DEFAULT_RETRY_ATTEMPTS, retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS,
) -> Any:
    """Calls the peer's `submit_audit` tool — note the `payload` kwarg
    name, the one exception to every other tool here using `message`."""
    return await _call_with_connect_retry(
        connection, "submit_audit", {"payload": envelope}, retry_attempts, retry_delay_seconds
    )


async def send_control(
    connection: PeerConnection, message: dict,
    retry_attempts: int = _DEFAULT_RETRY_ATTEMPTS, retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS,
) -> Any:
    """Calls the peer's `receive_control` tool."""
    return await _call_with_connect_retry(
        connection, "receive_control", {"message": message}, retry_attempts, retry_delay_seconds
    )
