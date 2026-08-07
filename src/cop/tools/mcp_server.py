"""FastMCP server exposing this peer's tool surface.

Two tools, PRD 4 "Revision 3" (`todoFullFix.md` §C3):

`receive_hint(text) -> dict` — a peer's natural-language tactical hint
(rule 26, possibly a lie, Table 21's `Intent` flag). Rule 25 means this
never decides anything: it validates `text` respects `hint_word_limit`
(Table 14 #2) and acknowledges — same shape as PRD 2's `receive_position`
validated board bounds, not a new pattern.

`share_scent_map() -> dict` — this peer's own current `ScentField`, exposed
as structured numeric data. Ch. 6.4/6.5's own architecture: "the client uses
a Tool against the FastMCP server to gather data... receives the opponent's
scent map" — a dedicated data channel, not the natural-language hint.
Supersedes Revision 1/2's `scent_report` string field, which squeezed this
same data through a lossy compass-direction sentence riding inside
`receive_hint` — a shape this repo's own re-read of the book found was
never mandated (`PRD-4-language-and-scent.md`'s Revision 3 section,
`WIRE-CONTRACT.md`). Rule 26/27 legality: not a numeric *position*
protocol — the sender's own environmental residue, whose formula is meant
to be shared and cryptographically locked between the two teams (ch. 4.5),
never a claim about where either agent actually is. Checked explicitly
against rules 26/27 by `rule-auditor` before this shape was treated as
settled (§C7), not assumed safe by analogy alone.

PRD 2's temporary bare-coordinate `receive_position` tool (legal only until
PRD 4 shipped the real natural-language tool, per CLAUDE.md's "Known trap")
is gone; neither tool here has a `col`/`row` parameter.

`on_receive` is an optional hook, called with the caller's IP (`str | None`)
on every successful call to *either* tool — the Orchestrator wires it to
feed both the watchdog's `heartbeat()` (rule 7) and a `connection_received`
trace log entry (rule 10's milestone: confirm a genuinely remote peer, not
`127.0.0.1`/LAN-local). `_caller_ip()` prefers `X-Forwarded-For` — what a
tunnel actually inserts; the raw ASGI `request.client.host` is always
`127.0.0.1` once a tunnel is in front — falling back to `request.client.host`
for direct localhost/LAN testing, and `None` when there's no active HTTP
request (unit tests use FastMCP's in-process transport, no HTTP layer).

`on_hint` is called with `(text,)` — narrowed from `(text, scent_report)` —
on every successful `receive_hint`. `get_scent_field` is called with no
arguments on every `share_scent_map` call, returning this peer's current
`dict[Position, float]` (typically `self.scent_field.full_field()`). Both
kept as injected callbacks rather than importing `reasoning.hint`/
`memory.scent` directly here — `tools/` stays a thin transport layer
(rule 3/I2), the Orchestrator owns wiring belief updates.
"""

from __future__ import annotations

from collections.abc import Callable

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers, get_http_request

from ..domain.board import Position
from ..shared.config import GameConfig
from .scent_wire import serialize_scent_field


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
    on_hint: Callable[[str], None] | None = None,
    get_scent_field: Callable[[], dict[Position, float]] | None = None,
) -> FastMCP:
    """Construct a fresh FastMCP server bound to this config's hint word limit."""
    mcp = FastMCP(name)

    @mcp.tool
    def receive_hint(text: str) -> dict:
        """Accept a peer's tactical hint; ack, or flag it as over the word limit."""
        if on_receive is not None:
            on_receive(_caller_ip())
        if on_hint is not None:
            on_hint(text)
        word_count = len(text.split())
        accepted = word_count <= config.hint_word_limit
        return {"accepted": accepted, "word_count": word_count}

    @mcp.tool
    def share_scent_map() -> dict:
        """Return this peer's own current scent field, wire-serialized —
        the data channel ch. 6.4/6.5 describe, not the verbal hint."""
        if on_receive is not None:
            on_receive(_caller_ip())
        field = get_scent_field() if get_scent_field is not None else {}
        return serialize_scent_field(field)

    return mcp
