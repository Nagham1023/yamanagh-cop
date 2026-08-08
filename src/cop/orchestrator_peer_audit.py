"""PRD 7's bilateral mutual audit wiring — closes PRD 6's own "Known gap"
for real (`PRD-7-reporting-shell.md`'s Design Question 11). Split into its
own mixin file rather than growing `orchestrator_turn.py`/
`orchestrator_peer.py` further past the 150-line cap.

Records the peer's own committed-and-revealed data (`on_commit`, plus this
side's own persisted half of `on_reveal` in `orchestrator_turn.py`, plus
`on_final_reveal`) into `self.peer_trace`; sends this side's own Final
Reveal; runs the real peer-side audit. Final Reveal happens once, at game
end (ch. 5.3.2), genuinely outside the per-turn `PeerStateMachine` cycle
(PRD 6 Design Question 4) — this mixin never transitions `self.state_machine`
at all, unlike every per-turn network call elsewhere in this repo.
"""

from __future__ import annotations

from .domain.board import Position
from .integrity.audit import AuditResult
from .integrity.peer_trace import run_peer_audit
from .planner.deadline import await_with_deadline
from .tools.mcp_client_prd6 import send_final_reveal


class PeerAuditMixin:
    def _on_commit_received(self, h_commit: str) -> None:
        """Server-role counterpart to `commit_and_reveal_to_peer`'s outgoing
        commit — persists the peer's own `Hcommit` into `self.peer_trace`,
        the piece PRD 6 left unwired (`on_commit` was always `None`)."""
        self.peer_trace.record_commit(h_commit)
        self.trace.log("peer_commit_received", h_commit=h_commit)

    def _on_final_reveal_received(self, nonces: dict, intents: dict) -> None:
        """Server-role counterpart to `send_final_reveal_to_peer` — the
        peer's own nonces and Intent flags, both required to recompute
        their `Hcommit` (ch. 5.3.1's equation needs `Intent`, not just
        `Nonce`; `State` is never sent at all, see `peer_trace.py`)."""
        self.peer_trace.record_final_reveal(nonces, intents)
        self.trace.log("peer_final_reveal_received", step_count=len(nonces))

    async def send_final_reveal_to_peer(self, peer_url: str) -> dict:
        """Rule 18: only ever called at game end. No state-machine
        transition here — Final Reveal sits outside the per-turn cycle
        entirely (PRD 6 Design Question 4), so there is no legal per-turn
        state for a failure here to land on; a failure is logged and
        re-raised, not converted into `TECHNICAL_LOSS`."""
        nonces = {str(step): nonce for step, nonce in self._pending_nonces.items()}
        intents = {str(step): intent for step, intent in self._pending_intents.items()}
        try:
            result = await await_with_deadline(
                send_final_reveal(peer_url, nonces, intents),
                timeout_seconds=self.config.response_timeout_seconds,
            )
        except Exception as exc:
            self.trace.log(
                "final_reveal_failed", reason=str(exc), exception_type=type(exc).__name__
            )
            raise
        self.trace.log("final_reveal_sent", step_count=len(nonces))
        return result

    def audit_peer(self) -> AuditResult:
        """The genuinely bilateral half of rule 19/36 — this side's own
        assembled record of what the peer (thief) committed to and
        revealed, verified against their own publicly known start
        position (`config.thief_start`, part of the shared, locked config —
        never received as a position claim over the wire, rule 27)."""
        peer_start = Position(*self.config.thief_start)
        return run_peer_audit(self.peer_trace, peer_start, self.board, self.config.barrier_quota)
