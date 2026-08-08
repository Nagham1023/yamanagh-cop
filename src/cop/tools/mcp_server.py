"""FastMCP server exposing this peer's tool surface.

`share_scent_map() -> dict` — this peer's own current `ScentField`, exposed
as structured numeric data. Ch. 6.4/6.5's own architecture: "the client uses
a Tool against the FastMCP server to gather data... receives the opponent's
scent map" — a dedicated data channel, not the natural-language hint.
Rule 26/27 legality: not a numeric *position* protocol — the sender's own
environmental residue, whose formula is meant to be shared and
cryptographically locked between the two teams (ch. 4.5), never a claim
about where either agent actually is. Checked explicitly against rules
26/27 by `rule-auditor` before this shape was treated as settled
(`todoFullFix.md` §C7), not assumed safe by analogy alone. `get_scent_field`
is the Orchestrator's `_get_and_commit_scent_field` (`orchestrator_peer.py`,
PRD 6) — computes and logs this turn's scent-map commitment hash at the
moment it's shared, closing rule 19/23's audit-half gap.

PRD 6's six new tools (`receive_commit`, `receive_reveal`,
`receive_final_reveal`, `receive_barrier_declaration`,
`receive_capture_claim`, `receive_capture_response`) live in
`mcp_server_prd6.py`, registered onto this same `FastMCP` instance —
split out for the 150-line house cap, not a separate server. PRD 9's one
new tool, `receive_step0` (ch. 5.5's negotiation ceremony, rules 11/23/49),
lives in `mcp_server_prd9.py`, same reasoning.
`receive_reveal(move, hint_text)` supersedes PRD 4's `receive_hint(text)`
in this same commit (see that module's own docstring for why) — PRD 2's
temporary bare-coordinate `receive_position` tool (legal only until PRD 4
shipped the real natural-language tool, per CLAUDE.md's "Known trap") is
also gone; nothing left on this surface has a `col`/`row` parameter
standing in for a position claim outside rules 15/16/21/22's own explicit
disclosure requirements.

`on_receive` is an optional hook, called with the caller's IP (`str | None`)
on every successful call to *any* tool on this surface — the Orchestrator
wires it to feed both the watchdog's `heartbeat()` (rule 7) and a
`connection_received` trace log entry (rule 10's milestone: confirm a
genuinely remote peer, not `127.0.0.1`/LAN-local). `_caller_ip()` prefers
`X-Forwarded-For` — what a tunnel actually inserts; the raw ASGI
`request.client.host` is always `127.0.0.1` once a tunnel is in front —
falling back to `request.client.host` for direct localhost/LAN testing, and
`None` when there's no active HTTP request (unit tests use FastMCP's
in-process transport, no HTTP layer).

Every PRD 6 callback (`on_commit`, `on_reveal`, ...) is injected the same
way `on_hint`/`get_scent_field` always were — `tools/` stays a thin
transport layer (rule 3/I2), the Orchestrator owns wiring belief/commit
state.
"""

from __future__ import annotations

from collections.abc import Callable

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers, get_http_request

from ..domain.board import Position
from ..shared.config import GameConfig
from .mcp_server_prd6 import register_prd6_tools
from .mcp_server_prd9 import register_prd9_tools
from .scent_wire import serialize_scent_field


def _caller_ip() -> str | None:
    """See the module docstring's `on_receive` paragraph for the
    X-Forwarded-For-first reasoning. `get_http_headers()` never raises even
    with no active HTTP request; `get_http_request()` does, hence the
    explicit catch."""
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
    get_scent_field: Callable[[], dict[Position, float]] | None = None,
    on_commit: Callable[[str], None] | None = None,
    on_reveal: Callable[[dict, str], None] | None = None,
    on_final_reveal: Callable[[dict], None] | None = None,
    on_barrier_declaration: Callable[[int, int], None] | None = None,
    on_capture_claim: Callable[[int, int, int, int, int], None] | None = None,
    on_capture_response: Callable[[bool, int, int], None] | None = None,
    on_step0: Callable[[dict, str, dict], dict] | None = None,
) -> FastMCP:
    """Construct a fresh FastMCP server bound to this config's hint word
    limit, with every PRD 1-6 tool registered."""
    mcp = FastMCP(name)

    @mcp.tool
    def share_scent_map() -> dict:
        """Return this peer's own current scent field, wire-serialized —
        the data channel ch. 6.4/6.5 describe, not the verbal hint."""
        if on_receive is not None:
            on_receive(_caller_ip())
        field = get_scent_field() if get_scent_field is not None else {}
        return serialize_scent_field(field)

    register_prd6_tools(
        mcp,
        config,
        _caller_ip,
        on_receive,
        on_commit=on_commit,
        on_reveal=on_reveal,
        on_final_reveal=on_final_reveal,
        on_barrier_declaration=on_barrier_declaration,
        on_capture_claim=on_capture_claim,
        on_capture_response=on_capture_response,
    )
    register_prd9_tools(mcp, _caller_ip, on_receive, on_step0=on_step0)

    return mcp
