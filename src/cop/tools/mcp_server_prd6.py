"""PRD 6's six new server-side tools — split out of `mcp_server.py`, which
would otherwise cross the 150-line house cap once these landed alongside
the PRD 1-5 surface. Registers onto an already-constructed `FastMCP`
instance (`mcp_server.py::build_server` calls this) rather than building
its own server, so both files share one `_caller_ip()`/`on_receive` wiring.

Every tool here follows the same shape the existing surface already
established (`receive_hint`, `share_scent_map`): a synchronous ack, an
injected callback (`tools/` stays a thin transport layer, rule 3/I2 — the
Orchestrator owns what happens with the data), flat scalar/dict parameters
only (rule 26/27: never a numeric *position claim* about either agent's
current whereabouts disguised as something else — `receive_barrier_declaration`
and the capture tools *are* explicit positions, which is exactly what rules
15/16/21/22 require disclosing, not a rule 27 violation).

`receive_reveal(move, hint_text)` supersedes PRD 4's `receive_hint(text)` —
ch. 5.3.2's own Step 3 payload is "Move + Hint" together, cryptographically
bound to the same commit; carrying the hint separately (the old channel)
would let it travel un-bound to any specific commit. `receive_hint` is
removed in the same commit this lands (`mcp_server.py`), matching this
project's own supersession discipline (`RULE-27-REMOVE-AT-PRD-4`'s
precedent) rather than leaving two parallel, ambiguous channels live.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP


def register_prd6_tools(
    mcp: FastMCP,
    config: Any,
    caller_ip: Callable[[], str | None],
    on_receive: Callable[[str | None], None] | None,
    on_commit: Callable[[str], None] | None = None,
    on_reveal: Callable[[dict, str], None] | None = None,
    on_final_reveal: Callable[[dict, dict], None] | None = None,
    on_barrier_declaration: Callable[[int, int], None] | None = None,
    on_capture_claim: Callable[[int, int, int, int, int], None] | None = None,
    on_capture_response: Callable[[bool, int, int], None] | None = None,
) -> None:
    """Attach every PRD 6 tool to `mcp`. All callback params default to
    `None` (a no-op) — tests that only care about a subset of PRD 6's
    surface don't need to stub every callback."""

    @mcp.tool
    def receive_commit(h_commit: str) -> dict:
        """Step 1/2 (ch. 5.3.2): accept a peer's `Hcommit` for this turn;
        acknowledge — the Acknowledge step is this synchronous return, not a
        separate tool/state (PRD 6 Design Question 4)."""
        if on_receive is not None:
            on_receive(caller_ip())
        if on_commit is not None:
            on_commit(h_commit)
        return {"acknowledged": True}

    @mcp.tool
    def receive_reveal(move: dict, hint_text: str) -> dict:
        """Step 3: `Move` (an unverified claim until Final Reveal, PRD 6
        Design Question 2) plus the tactical hint — no `nonce` parameter,
        rule 18: the nonce stays hidden until `receive_final_reveal`."""
        if on_receive is not None:
            on_receive(caller_ip())
        if on_reveal is not None:
            on_reveal(move, hint_text)
        word_count = len(hint_text.split())
        accepted = word_count <= config.hint_word_limit
        return {"accepted": accepted, "word_count": word_count}

    @mcp.tool
    def receive_final_reveal(nonces: dict, intents: dict) -> dict:
        """Step 4, end-of-game only: every one of this peer's own nonces
        *and* Intent flags for the whole match, both keyed by step number as
        a string (JSON object keys are always strings). `Intent` — like the
        nonce — is never revealed earlier (ch. 5.3.1's own `Hcommit`
        equation needs it to recompute the hash; `move`/`hint_text` alone,
        already revealed at Step 3, aren't enough). `State` is deliberately
        *not* part of this payload at all: the auditing side reconstructs it
        locally by replaying the peer's own revealed `Move` sequence from
        their publicly known start position (`board_and_agents.thief_start`/
        `cop_start`, part of the shared, locked config) — never transmitted
        as a position claim, matching rule 27. Enables
        `integrity/peer_trace.py::run_peer_audit`'s full bilateral replay.

        Return includes the peer-audit summary (rules 19/36) when the
        orchestrator callback provides one — so the revealing side learns
        whether this side verified their commits, closing the silent
        one-way audit gap."""
        if on_receive is not None:
            on_receive(caller_ip())
        result: dict = {"acknowledged": True}
        if on_final_reveal is not None:
            audit = on_final_reveal(nonces, intents)
            if isinstance(audit, dict):
                result.update(audit)
        return result

    @mcp.tool
    def receive_barrier_declaration(col: int, row: int) -> dict:
        """Rule 15: truthful, same-turn disclosure of a barrier placement's
        exact cell. Rule 16 (never lying about it) is enforced by folding
        this into that turn's commit, checked at final audit — not here."""
        if on_receive is not None:
            on_receive(caller_ip())
        if on_barrier_declaration is not None:
            on_barrier_declaration(col, row)
        return {"acknowledged": True}

    @mcp.tool
    def receive_capture_claim(
        thief_col: int, thief_row: int, cop_col: int, cop_row: int, claimed_at_step: int
    ) -> dict:
        """Rule 21: a capture claim, wire-flattened from
        `integrity.capture_protocol.CaptureClaim`. Acknowledges receipt only
        — the truthful confirm/deny travels back later, as its own commit,
        via `receive_capture_response` (not this call's return value)."""
        if on_receive is not None:
            on_receive(caller_ip())
        if on_capture_claim is not None:
            on_capture_claim(thief_col, thief_row, cop_col, cop_row, claimed_at_step)
        return {"acknowledged": True}

    @mcp.tool
    def receive_capture_response(confirmed: bool, true_thief_col: int, true_thief_row: int) -> dict:
        """Rule 22: the truthful answer to an earlier `receive_capture_claim`
        — wire-flattened from `CaptureResponse`."""
        if on_receive is not None:
            on_receive(caller_ip())
        if on_capture_response is not None:
            on_capture_response(confirmed, true_thief_col, true_thief_row)
        return {"acknowledged": True}
