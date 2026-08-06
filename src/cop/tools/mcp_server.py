"""FastMCP server exposing this peer's tool surface.

One tool: `receive_hint(text, scent_report)` — a peer's natural-language
tactical hint (rule 26, possibly a lie, Table 21's `Intent` flag) plus its
always-truthful scent-report companion (Revision 1, PRD 4 Design Question
1 — declared-truthful, never subject to `Intent`). Rule 25 means this never
decides anything: it validates each field respects `hint_word_limit`
(Table 14 #2) independently and acknowledges — same shape as PRD 2's
`receive_position` validated board bounds, not a new pattern.

PRD 2's temporary bare-coordinate `receive_position` tool (legal only until
PRD 4 shipped the real natural-language tool, per CLAUDE.md's "Known trap")
is gone. Rule 27 (no numeric position protocol) is fatal; this tool's
signature has no `col`/`row` parameter at all, which is the actual,
unbeatable guarantee (not a grep of the text) — and stays true here even
though the payload doubled to two fields, since both are still plain
strings, no numeric structure ever serialized.

`on_receive` is an optional hook, called with the caller's IP (`str | None`)
on every successful call — the Orchestrator wires it to feed both the
watchdog's `heartbeat()` (rule 7 needs something real to measure staleness
against) and a `connection_received` trace log entry (rule 10's milestone:
confirm a genuinely remote peer connected, not `127.0.0.1`/LAN-local).
`_caller_ip()` prefers the `X-Forwarded-For` header — what a tunnel
actually inserts; the raw ASGI `request.client.host` is always `127.0.0.1`
once a tunnel is in front (the tunnel's own local forwarding client, never
the real remote caller) — falling back to `request.client.host` for direct
localhost/LAN testing with no tunnel, and to `None` when there is no active
HTTP request at all (every existing unit test calls tools through
FastMCP's in-process `Client(mcp)` transport, which has no HTTP layer to
read a header from).

`on_hint` is a second, independent optional hook, called with `(text,
scent_report)` on every successful call — the Orchestrator wires it to
interpret both and update the belief map (the tactical hint via
`update_from_hint`, the scent report via the more-trusted
`update_from_scent_report`). Kept as an injected callback rather than
importing `reasoning.hint`/`memory.belief` directly here: this module stays
a thin transport layer (rule 3/I2 — the Orchestrator, not `tools/`, owns
wiring belief updates), and it keeps `receive_hint` testable without
constructing a full belief map for every unit test.
"""

from __future__ import annotations

from collections.abc import Callable

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers, get_http_request

from ..shared.config import GameConfig


def _caller_ip() -> str | None:
    """See `on_receive`'s docstring above for the X-Forwarded-For-first
    reasoning. `get_http_headers()` never raises even with no active HTTP
    request; `get_http_request()` does, hence the explicit catch."""
    forwarded = get_http_headers().get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    try:
        request = get_http_request()
    except RuntimeError:
        return None
    return request.client.host if request.client else None


def build_server(
    config: GameConfig,
    name: str = "cop_peer",
    on_receive: Callable[[str | None], None] | None = None,
    on_hint: Callable[[str, str], None] | None = None,
) -> FastMCP:
    """Construct a fresh FastMCP server bound to this config's hint word limit."""
    mcp = FastMCP(name)

    @mcp.tool
    def receive_hint(text: str, scent_report: str) -> dict:
        """Accept a peer's tactical hint and scent report; ack, or flag
        either as over the word limit."""
        if on_receive is not None:
            on_receive(_caller_ip())
        if on_hint is not None:
            on_hint(text, scent_report)
        word_count = len(text.split())
        scent_word_count = len(scent_report.split())
        accepted = word_count <= config.hint_word_limit and scent_word_count <= config.hint_word_limit
        return {"accepted": accepted, "word_count": word_count, "scent_word_count": scent_word_count}

    return mcp
