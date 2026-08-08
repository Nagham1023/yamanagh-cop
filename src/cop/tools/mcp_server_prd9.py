"""PRD 9's one new tool — split out the same way `mcp_server_prd6.py` was,
registered onto the already-constructed `FastMCP` instance
(`mcp_server.py::build_server` calls this).

`receive_step0` is a single synchronous round trip, unlike PRD 6's
commit/reveal split-callback shape: ch. 5.5's ceremony has no reason to be
asynchronous — both sides already hold everything they need (their own
`Step0Declaration`, computed offline) the instant the call arrives, so the
responder can verify and answer in the same call rather than acknowledging
now and replying later via a second, separate tool.
"""

from __future__ import annotations

from collections.abc import Callable

from fastmcp import FastMCP


def register_prd9_tools(
    mcp: FastMCP,
    caller_ip: Callable[[], str | None],
    on_receive: Callable[[str | None], None] | None,
    on_step0: Callable[[dict, str, dict], dict] | None = None,
) -> None:
    """Attach `receive_step0` to `mcp`. `on_step0` defaults to `None` (an
    inert ack) — tests exercising the rest of the surface don't need to
    stub Step-0 negotiation."""

    @mcp.tool
    def receive_step0(declaration: dict, signature: str, repos: dict) -> dict:
        """Ch. 5.5: the peer's own signed `Step0Declaration`, wire-
        flattened, plus its repo URLs (rule 49 — not part of the signed
        hash, the book's own Step-0 field list doesn't include it; rides
        alongside the same way `receive_reveal(move, hint_text)` already
        bundles two logically different things in one call). Returns this
        side's own `{declaration, signature, repos}` in the same response
        — `on_step0`'s own job is to verify the incoming payload *and*
        build that response (`orchestrator_step0.py::_on_step0_received`),
        not just to log receipt like every other `on_*` callback here."""
        if on_receive is not None:
            on_receive(caller_ip())
        if on_step0 is not None:
            return on_step0(declaration, signature, repos)
        return {"acknowledged": True}
