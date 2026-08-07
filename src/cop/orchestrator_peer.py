"""Orchestrator's peer-to-peer network calls — split out of orchestrator.py,
which grew past the 150-line house cap once PRD 4 "Revision 3" added the
scent-map Tool call alongside the existing hint exchange. A mixin, not a
standalone class: reaches into `self.trace`, `self.state_machine`,
`self.config`, and `self.watchdog`, all of which `Orchestrator.__init__`
sets up — this file only exists to keep `orchestrator.py` under the cap.
"""

from __future__ import annotations

from .domain.board import Position
from .planner.deadline import await_with_deadline
from .tools.mcp_client import request_scent_map, send_hint


class PeerCommsMixin:
    def _on_connection_received(self, ip: str | None) -> None:
        """Fires on every successful `receive_hint`/`share_scent_map` call
        (PRD 5): feeds the watchdog heartbeat (rule 7) and logs who
        connected (rule 10's milestone — confirm a genuinely remote peer,
        not 127.0.0.1/LAN)."""
        self.watchdog.heartbeat()
        self.trace.log("connection_received", ip=ip)

    async def request_scent_map_from_peer(self, peer_url: str) -> dict[Position, float]:
        """Client role: pull the peer's own scent field via the Tool-based
        data channel (ch. 6.4/6.5), not the verbal hint — PRD 4 "Revision 3"
        (`todoFullFix.md` §C4). Called before the tactical hint is sent,
        matching ch. 6.5's own "gather data via Tool, then build the prompt"
        ordering — a data-gathering pre-step, not part of the
        SENDING/AWAITING_RESPONSE move-commit protocol `send_to_peer` drives
        below. Same deadline-guard and technical-loss handling as
        `send_to_peer`; every state can reach `TECHNICAL_LOSS`
        (`state_machine.py`'s own transition table), so this needs no new
        states to fail cleanly from wherever `take_turn` is when it's called.

        Rule 9 — everything a peer sends is untrusted (rule-auditor
        finding): a malformed `share_scent_map` response
        (`scent_wire.deserialize_scent_field` raises `ValueError`) must
        *not* become our own technical loss — that would let a hostile or
        buggy peer force our forfeit just by returning garbage, on a
        connection that otherwise worked fine. Caught separately from a
        genuine network failure (connection refused, timeout) and degraded
        to an empty scent map instead, the same "reject malformed input,
        don't crash the turn on it" discipline `receive_hint`'s word-limit
        gating already applies on the receiving side.
        """
        self.trace.log("requesting_scent_map", peer_url=peer_url)
        try:
            scent_map = await await_with_deadline(
                request_scent_map(peer_url),
                timeout_seconds=self.config.response_timeout_seconds,
            )
        except ValueError as exc:
            self.trace.log("scent_map_malformed", peer_url=peer_url, reason=str(exc))
            return {}
        except Exception as exc:
            self.trace.log(
                "technical_loss",
                reason=str(exc),
                exception_type=type(exc).__name__,
                state=self.state_machine.state,
            )
            self.state_machine.transition("TECHNICAL_LOSS")
            raise
        self.trace.log("scent_map_received", cell_count=len(scent_map))
        return scent_map

    async def send_to_peer(self, peer_url: str, text: str) -> dict:
        """Client role: send a natural-language hint to the peer, deadline-guarded,
        state-machine-tracked (rule 26/27 — no coordinates, ever, past this point).

        On *any* failure to get a response — a deadline expiry, or the peer
        being gone entirely (connection refused/reset, e.g. a killed
        process) — this transitions to `TECHNICAL_LOSS`, logs why, and
        re-raises. A killed peer is caught by a live TCP handshake failing
        immediately, not by the timeout; only catching `DeadlineExceededError`
        here would leave the state machine stuck in `AWAITING_RESPONSE` and
        nothing logged for that case — exactly the "hang, not a clean loss"
        rule 6/7 exist to prevent. The caller decides what happens next;
        this method's job is only to make the loss real and recorded.
        """
        self.state_machine.transition("SENDING")
        self.trace.log("sending_hint", peer_url=peer_url, text=text)

        self.state_machine.transition("AWAITING_RESPONSE")
        try:
            result = await await_with_deadline(
                send_hint(peer_url, text),
                timeout_seconds=self.config.response_timeout_seconds,
            )
        except Exception as exc:
            self.trace.log(
                "technical_loss",
                reason=str(exc),
                exception_type=type(exc).__name__,
                state=self.state_machine.state,
            )
            self.state_machine.transition("TECHNICAL_LOSS")
            raise

        self.state_machine.transition("TURN_RESOLVED")
        self.trace.log("turn_resolved", result=result)
        self.state_machine.transition("WAITING_FOR_OPPONENT")
        return result
