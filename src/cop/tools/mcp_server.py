"""FastMCP server exposing this peer's tool surface.

One tool: `receive_hint(text)` — a peer's natural-language hint (rule 26).
Rule 25 means this never decides anything: it validates the hint respects
`hint_word_limit` (Table 14 #2) and acknowledges — same shape as PRD 2's
`receive_position` validated board bounds, not a new pattern.

PRD 2's temporary bare-coordinate `receive_position` tool (legal only until
this layer shipped the real natural-language tool, per CLAUDE.md's "Known
trap") is gone. Rule 27 (no numeric position protocol) is fatal; this
tool's signature has no `col`/`row` parameter at all, which is the actual,
unbeatable guarantee (not a grep of the text).

`on_receive` is an optional hook, called on every successful call — the
Orchestrator wires it to the watchdog's `heartbeat()` so rule 7's watchdog
has something real to measure staleness against (activity from the peer),
not just wall-clock time since process start.

`on_hint` is a second, independent optional hook, called with the raw hint
text on every successful call — the Orchestrator wires it to interpret the
peer's hint and update the belief map. Kept as an injected callback rather
than importing `reasoning.hint`/`memory.belief` directly here: this module
stays a thin transport layer (rule 3/I2 — the Orchestrator, not `tools/`,
owns wiring belief updates), and it keeps `receive_hint` testable without
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
    on_hint: Callable[[str], None] | None = None,
) -> FastMCP:
    """Construct a fresh FastMCP server bound to this config's hint word limit."""
    mcp = FastMCP(name)

    @mcp.tool
    def receive_hint(text: str) -> dict:
        """Accept a peer's natural-language hint; ack, or flag it as over the word limit."""
        if on_receive is not None:
            on_receive()
        if on_hint is not None:
            on_hint(text)
        word_count = len(text.split())
        accepted = word_count <= config.hint_word_limit
        return {"accepted": accepted, "word_count": word_count}

    return mcp
