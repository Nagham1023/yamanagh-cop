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

`on_receive` is an optional hook, called on every successful call — the
Orchestrator wires it to the watchdog's `heartbeat()` so rule 7's watchdog
has something real to measure staleness against (activity from the peer),
not just wall-clock time since process start.

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

from ..shared.config import GameConfig


def build_server(
    config: GameConfig,
    name: str = "cop_peer",
    on_receive: Callable[[], None] | None = None,
    on_hint: Callable[[str, str], None] | None = None,
) -> FastMCP:
    """Construct a fresh FastMCP server bound to this config's hint word limit."""
    mcp = FastMCP(name)

    @mcp.tool
    def receive_hint(text: str, scent_report: str) -> dict:
        """Accept a peer's tactical hint and scent report; ack, or flag
        either as over the word limit."""
        if on_receive is not None:
            on_receive()
        if on_hint is not None:
            on_hint(text, scent_report)
        word_count = len(text.split())
        scent_word_count = len(scent_report.split())
        accepted = word_count <= config.hint_word_limit and scent_word_count <= config.hint_word_limit
        return {"accepted": accepted, "word_count": word_count, "scent_word_count": scent_word_count}

    return mcp
