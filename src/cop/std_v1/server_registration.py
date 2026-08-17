"""`register_std_v1_tools`: attaches the spec's four tools (Section 7) onto
a dedicated `FastMCP` instance built specifically for a std_v1 match — a
separate server from `tools/mcp_server.py`'s own native-protocol one
(`std_v1_peer.py` builds and runs it), so there is no name collision to
resolve the way `thief_peer.interop.std_v1.server_registration` had to
handle on its own side (that repo's native `negotiate`/`submit_audit`/
`receive_control` tools already existed on the same shared server; this
repo's own native tool names never collide with the spec's).
"""

from __future__ import annotations

from fastmcp import FastMCP

from .exchange import StdExchange


def register_std_v1_tools(mcp: FastMCP, exchange: StdExchange) -> None:
    """Registers all four std_v1 tools onto `mcp`, each simply enqueuing
    onto `exchange` and acking immediately — Section 7 requires every
    receive tool to validate lightly, enqueue, and return `{"ok": true}`
    right away, never block on anything downstream."""

    @mcp.tool
    def negotiate(message: dict) -> dict:
        """Section 3: the peer's own negotiation offer for one sub-game."""
        exchange.record_offer(message)
        return {"ok": True}

    @mcp.tool
    def receive_turn(message: dict) -> dict:
        """Section 9: one sealed turn message from the peer."""
        exchange.record_turn(message)
        return {"ok": True}

    @mcp.tool
    def submit_audit(payload: dict) -> dict:
        """Section 10: a per-sub-game audit envelope, or the final
        series-consensus envelope — note the `payload` kwarg name, this
        tool's one exception to the spec's usual `message` naming."""
        exchange.record_audit(payload)
        return {"ok": True}

    @mcp.tool
    def receive_control(message: dict) -> dict:
        """An out-of-band control message from the peer."""
        exchange.record_control(message)
        return {"ok": True}
