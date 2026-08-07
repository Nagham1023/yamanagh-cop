"""Orchestrator's peer-to-peer network calls — split out of orchestrator.py,
which grew past the 150-line house cap once PRD 4 "Revision 3" added the
scent-map Tool call alongside the existing hint exchange. A mixin, not a
standalone class: reaches into `self.trace`, `self.state_machine`,
`self.config`, and `self.watchdog`, all of which `Orchestrator.__init__`
sets up — this file only exists to keep `orchestrator.py` under the cap.

PRD 6's real Commit-Reveal round trip (`commit_and_reveal_to_peer`) lives in
`orchestrator_commit_reveal.py`'s `CommitRevealMixin`, split out separately
once it needed its own room — it calls `_fail_to_technical_loss` below,
shared across both mixins rather than duplicated a third time.
"""

from __future__ import annotations

from .domain.board import Position
from .integrity.scent_commitment import commit_scent_map
from .planner.deadline import await_with_deadline
from .tools.mcp_client import request_scent_map


class PeerCommsMixin:
    def _on_connection_received(self, ip: str | None) -> None:
        """Fires on every successful tool call on this peer's own server
        (PRD 5): feeds the watchdog heartbeat (rule 7) and logs who
        connected (rule 10's milestone — confirm a genuinely remote peer,
        not 127.0.0.1/LAN)."""
        self.watchdog.heartbeat()
        self.trace.log("connection_received", ip=ip)

    def _fail_to_technical_loss(self, exc: Exception) -> None:
        """Shared by every network call in `PeerCommsMixin`/
        `CommitRevealMixin`: log why, then transition — the caller still
        re-raises immediately after, this only makes the loss real and
        recorded (rule 6/7's "a clean loss, not a hang")."""
        self.trace.log(
            "technical_loss",
            reason=str(exc),
            exception_type=type(exc).__name__,
            state=self.state_machine.state,
        )
        self.state_machine.transition("TECHNICAL_LOSS")

    def _get_and_commit_scent_field(self) -> dict[Position, float]:
        """`build_server`'s `get_scent_field` callback: computes and logs
        this turn's scent map commitment hash at the moment it's actually
        shared (rule 19/23's audit half), rather than trusting the field on
        honest-by-construction grounds alone. Logged
        here (the sender's own trace) rather than sent as a new real-time
        wire field — matches how every other integrity fact in this repo
        already lives in the trace log for later audit
        (`integrity/audit.py`)."""
        field = self.scent_field.full_field()
        commit_hash = commit_scent_map(field)
        self.trace.log("scent_map_shared", commit_hash=commit_hash, cell_count=len(field))
        return field

    async def request_scent_map_from_peer(self, peer_url: str) -> dict[Position, float]:
        """Client role: pull the peer's own scent field via the Tool-based
        data channel (ch. 6.4/6.5), not the verbal hint — PRD 4 "Revision 3"
        (`todoFullFix.md` §C4). Called before the tactical hint is sent,
        matching ch. 6.5's own "gather data via Tool, then build the prompt"
        ordering — a data-gathering pre-step, not part of the
        COMMITTING/AWAITING_REVEAL move-commit protocol
        `commit_and_reveal_to_peer` drives. `orchestrator_turn.py`'s
        `take_turn` transitions to `COMPUTING_MOVE` *before* calling this,
        specifically so this call's own failure path has a legal
        `TECHNICAL_LOSS` edge to use — PRD 6's narrower table
        (`state_machine.py`'s own docstring) dropped the old blanket
        `WAITING_FOR_OPPONENT -> TECHNICAL_LOSS` edge this method used to
        rely on when called any earlier.

        Rule 9 — everything a peer sends is untrusted (rule-auditor
        finding): a malformed `share_scent_map` response
        (`scent_wire.deserialize_scent_field` raises `ValueError`) must
        *not* become our own technical loss — that would let a hostile or
        buggy peer force our forfeit just by returning garbage, on a
        connection that otherwise worked fine. Caught separately from a
        genuine network failure (connection refused, timeout) and degraded
        to an empty scent map instead, the same "reject malformed input,
        don't crash the turn on it" discipline `receive_reveal`'s
        word-limit gating already applies on the receiving side.
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
            self._fail_to_technical_loss(exc)
            raise
        self.trace.log("scent_map_received", cell_count=len(scent_map))
        return scent_map
