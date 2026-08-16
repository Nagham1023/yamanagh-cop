"""PRD 8's capture-claim send-and-await (rules 21/22) — split out of
`orchestrator_commit_reveal.py`, which would otherwise cross the 150-line
house cap once this landed. Called from *inside*
`CommitRevealMixin.commit_and_reveal_to_peer`'s own `AWAITING_REVEAL`
window, sibling to the existing barrier-declaration block — not a separate
post-hoc call from the game loop, and not a new state-machine state
(PRD-8-live-match-wiring.md's own Design Question 2, corrected there before
this file was written): `AWAITING_REVEAL` already has the `TECHNICAL_LOSS`
edge this wait needs, exactly the same reasoning PRD 6 already used for
barrier declaration.

Reaches into `self.trace`, `self.config`, `self.game_state`,
`self._capture_response_event`, `self._capture_response`,
`self._capture_response_loop`, `self._last_turn_captured` (all set up by
`Orchestrator.__init__`), plus `self._fail_to_technical_loss` from the
sibling `PeerCommsMixin`.

`self._capture_response_loop`: found only by actually running the honest
and adversarial exchanges live, not by design review — `asyncio.Event.set()`
is not thread-safe. The claiming side awaits the event inside its own
`asyncio.run(...)` call (one event loop); the response arrives via this
side's own MCP *server*, which runs in a genuinely separate OS thread with
its own event loop (`run_as_server`, every test in this repo). Calling
`.set()` directly from the server's thread never wakes a waiter parked in a
different loop — it silently does nothing, producing a real, reproducible
hang (confirmed by running the "wrong belief" test under an explicit
`timeout`, not by reasoning about asyncio alone). Fixed the standard way:
the claiming side records which loop it's waiting on before it waits, and
the receiving callback schedules `.set()` onto that exact loop via
`call_soon_threadsafe`, the only thread-safe way to signal across loops.
"""

from __future__ import annotations

import asyncio

from .domain.board import Position
from .integrity.capture_protocol import CaptureResponse, claim_capture
from .planner.deadline import await_with_deadline
from .reasoning.brain_base import Action
from .reasoning.state import claims_capture
from .tools.mcp_client_prd6 import send_capture_claim


class CaptureClaimMixin:
    async def _claim_capture_if_warranted(
        self, peer_url: str, action: Action, believed_thief_pos: Position | None, step: int
    ) -> None:
        """No-op if this turn's action didn't land on the belief target
        (Design Question 1: the cop can only ever claim its own believed
        cell, never a verified one). Otherwise sends the claim, then waits
        on the peer's own independent `receive_capture_response` callback
        (Design Question 2 — not a simple request/response) with a
        deadline; a timeout reaches `TECHNICAL_LOSS` via the caller's own
        still-active `AWAITING_REVEAL` state, not a new one."""
        self._capture_response_event.clear()
        self._capture_response = None
        self._last_turn_captured = False

        if believed_thief_pos is None:
            return
        claimed_cell = claims_capture(
            action, self.game_state.own_pos, self.game_state.own_pos, believed_thief_pos
        )
        if claimed_cell is None:
            return

        connection = self._get_peer_connection(peer_url)
        claim = claim_capture(
            thief_pos=claimed_cell, cop_pos=self.game_state.own_pos, claimed_at_step=step
        )
        # Set *before* the send, not after (rule-auditor finding): a
        # response arriving between the send completing and this line
        # would otherwise find `_capture_response_loop` still `None` and
        # silently skip waking the waiter, stalling for the full deadline
        # even though the response had already arrived correctly.
        self._capture_response_loop = asyncio.get_running_loop()
        try:
            await await_with_deadline(
                send_capture_claim(
                    connection,
                    claim.thief_pos.col,
                    claim.thief_pos.row,
                    claim.cop_pos.col,
                    claim.cop_pos.row,
                    claim.claimed_at_step,
                ),
                timeout_seconds=self.config.response_timeout_seconds,
            )
        except Exception as exc:
            self._fail_to_technical_loss(exc)
            raise
        self.trace.log("capture_claimed", thief_pos=repr(claimed_cell), step=step)

        try:
            await await_with_deadline(
                self._capture_response_event.wait(),
                timeout_seconds=self.config.response_timeout_seconds,
            )
        except Exception as exc:
            self._fail_to_technical_loss(exc)
            raise

        confirmed = self._capture_response is not None and self._capture_response.confirmed
        self._last_turn_captured = confirmed
        self.trace.log("capture_response_received", confirmed=confirmed, step=step)

    def _on_capture_response_received(
        self, confirmed: bool, true_thief_col: int, true_thief_row: int
    ) -> None:
        """Server-role counterpart to `_claim_capture_if_warranted`'s
        outgoing claim — the peer's own independent, truthful answer
        (rule 22), wire-flattened from `CaptureResponse`. Sets the event
        `_claim_capture_if_warranted`'s own deadline-guarded wait is
        blocked on."""
        self._capture_response = CaptureResponse(
            confirmed=confirmed, true_thief_pos=Position(true_thief_col, true_thief_row)
        )
        loop = self._capture_response_loop
        if loop is not None:
            loop.call_soon_threadsafe(self._capture_response_event.set)
        self.trace.log("peer_capture_response_received", confirmed=confirmed)

    def _on_capture_claim_received(
        self, thief_col: int, thief_row: int, cop_col: int, cop_row: int, claimed_at_step: int
    ) -> None:
        """Design Question 3: this repo's own role never legitimately
        *receives* a claim — `domain/scoring.py`'s `Table 17` has no
        "thief captures cop" outcome, and this side has no true thief
        position to honestly answer one from. A defensive no-op: log it
        as untrusted, unexpected input (I9) and do nothing else —
        `receive_capture_claim`'s own ack already covers the wire reply,
        never fabricate a `CaptureResponse` here."""
        self.trace.log(
            "unexpected_capture_claim_received",
            thief_col=thief_col,
            thief_row=thief_row,
            cop_col=cop_col,
            cop_row=cop_row,
            claimed_at_step=claimed_at_step,
        )
