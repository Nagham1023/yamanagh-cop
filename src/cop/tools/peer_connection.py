"""One persistent connection per peer, reused across a whole match —
replaces the old "one `fastmcp.Client` per call" pattern (PRD 4-9's
`mcp_client*.py`), found live via a real cross-machine match that failed
consistently around round 5-6: roughly 19+ separate fresh TCP/TLS/MCP-
session handshakes accumulated by then through one free-tier ngrok
tunnel, and every "Client failed to connect" failure this session was
`fastmcp.Client._connect()`'s own wrapped-exception string for a *fresh*
connection attempt specifically (confirmed by reading the installed
library source) — never a failure on an already-open session.
`fastmcp.Client` is explicitly designed for the opposite of what this
repo did: enter `async with client:` once, call `call_tool(...)` many
times inside that one block, one `mcp-session-id` negotiated once.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastmcp import Client
from fastmcp.exceptions import ToolError

_CONNECT_ONLY_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout)
# `fastmcp.Client.session`'s own property getter (client.py) raises this
# verbatim, synchronously, before `self.session.call_tool(...)` can even
# construct the outbound call — evaluating `.session` is the first half of
# that expression, so a raise here means `call_tool` was never reached.
# Found live: a retried `send_commit` hit exactly this (not a bare
# ConnectError) one call after a prior attempt's force-close — the
# background session task had torn itself down between `_connect()`
# reporting ready and this call actually running, a narrow fastmcp-level
# race under a flaky tunnel, not anything this repo's own retry caused.
_SESSION_NOT_CONNECTED_MESSAGE = (
    "Client is not connected. Use the 'async with client:' context manager first."
)


def is_connect_only_failure(exc: Exception) -> bool:
    """True only when `exc` provably means the request was never
    transmitted — httpx raises `ConnectError`/`ConnectTimeout` solely
    while opening a connection, never once bytes are in flight (that's
    `ReadTimeout`/`WriteError`/`RemoteProtocolError` and siblings, where
    the peer may already have received and applied the call). Also
    matches `fastmcp.Client._connect()`'s own `RuntimeError("Client
    failed to connect: ...")` wrapper (chains the same underlying httpx
    exception as `__cause__`) and its `.session` property's own
    `_SESSION_NOT_CONNECTED_MESSAGE` — both fire before any bytes could
    have left this process. A real match confirmed the first gap: a bare
    `ConnectError` on an *already-open* `PeerConnection` (the pooled
    transport's own reconnect attempt failing, not the first handshake)
    still fits this definition — nothing was sent either way."""
    if isinstance(exc, _CONNECT_ONLY_ERRORS):
        return True
    if isinstance(exc.__cause__, _CONNECT_ONLY_ERRORS):
        return True
    return isinstance(exc, RuntimeError) and str(exc) == _SESSION_NOT_CONNECTED_MESSAGE


class PeerConnection:
    """Lazily connects on first `call_tool`, stays open across many calls,
    and auto-heals: a genuine connection failure force-closes the
    underlying client so the *next* call reconnects fresh, rather than
    `Client`'s own internals re-raising the same cached dead-session
    failure forever on a still-open block. A `ToolError` (a normal,
    well-formed tool-level rejection) is deliberately *not* treated as a
    connection failure — the session is fine, and `send_commit`/
    `send_reveal`'s own pre-PRD-15 schema-fallback (`mcp_client_prd6.py`)
    depends on the session staying open after one."""

    def __init__(self, url: str) -> None:
        # Deliberately no `timeout=` here: `Client`'s own per-request read
        # timeout raises `mcp.shared.exceptions.McpError`, a different
        # type than `await_with_deadline`'s `DeadlineExceededError` — and
        # every call site already wraps its call in
        # `await_with_deadline(..., timeout_seconds=...)`, which fully
        # bounds it regardless (found live: a redundant inner timeout
        # raced the outer one and won, breaking `except
        # DeadlineExceededError` callers).
        self.url = url
        self._client = Client(url)
        self._connected = False

    async def __aenter__(self) -> PeerConnection:
        if not self._connected:
            await self._client.__aenter__()
            self._connected = True
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if not self._connected:
            await self._client.__aenter__()
            self._connected = True
        try:
            return await self._client.call_tool(name, arguments)
        except ToolError:
            raise
        except Exception:
            await self._client.close()
            self._connected = False
            raise

    async def close(self) -> None:
        if self._connected:
            await self._client.close()
            self._connected = False
