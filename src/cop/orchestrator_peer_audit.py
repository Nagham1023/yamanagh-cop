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
from .planner.deadline import DeadlineExceededError, await_with_deadline
from .tools.mcp_client_prd6 import send_final_reveal

# Algorithm/robustness constant, not an Appendix F quantity (I6 doesn't
# apply — same category as belief.py's _HINT_RELIABILITY): the real race
# this closes needed about 31ms of margin (a peer's Final Reveal landing
# just after this side's own outgoing send completed). This is a fixed
# short wait, deliberately *not* `response_timeout_seconds` (a full turn's
# compute+network budget, including LLM hint generation) — reusing that
# 30s figure made every report_game() call that doesn't simulate a real
# peer (most unit tests) pay a near-full timeout for no reason.
_PEER_FINAL_REVEAL_WAIT_SECONDS = 5.0


class PeerAuditMixin:
    def _on_final_reveal_received(self, nonces: dict, intents: dict) -> dict:
        """Server-role counterpart to `send_final_reveal_to_peer` — the
        peer's own nonces and Intent flags, both required to recompute
        their `Hcommit` (ch. 5.3.1's equation needs `Intent`, not just
        `Nonce`; `State` is never sent at all, see `peer_trace.py`).

        Ch.5.3.2 Step 4 names Final Reveal as the end-of-game step ("all
        Nonces (end of game)"). A live Cop⇄Thief run showed this callback
        used to only record audit data while `play_game` kept looping to
        the step ceiling — producing contradictory winners (rule 35). The
        flag below is what stops the loop.

        Returns the peer-audit summary (rules 19/36) so the caller of
        `receive_final_reveal` learns whether *their* commits verified —
        mutual audit cannot be one-sided and silent."""
        self.peer_trace.record_final_reveal(nonces, intents)
        self._peer_final_reveal_received = True
        if self._peer_final_reveal_loop is not None:
            # asyncio.Event.set() is not thread-safe across loops -- this
            # callback runs on the MCP server's own OS thread
            # (orchestrator_capture.py's docstring has the general
            # reasoning). call_soon_threadsafe is the only safe way to wake
            # a waiter parked on report_game()'s own loop.
            self._peer_final_reveal_loop.call_soon_threadsafe(self._peer_final_reveal_event.set)
        peer_audit = self.audit_peer()
        verified = len(self.peer_trace.entries) - len(peer_audit.mismatches)
        self.trace.log(
            "peer_final_reveal_received",
            step_count=len(nonces),
            audit_passed=peer_audit.passed,
            verified_steps=verified,
        )
        return {
            "passed": peer_audit.passed,
            "verified_steps": max(0, verified),
            "failed_steps": [m.get("step") for m in peer_audit.mismatches],
            "evaluated": True,
        }

    async def _await_peer_final_reveal(
        self, timeout_seconds: float = _PEER_FINAL_REVEAL_WAIT_SECONDS
    ) -> None:
        """`report_game()`'s own real fix for the race this module's other
        docstrings describe: don't call `audit_peer()` the instant this
        side's own outcome is known, since the peer's independently-timed
        Final Reveal may genuinely not have arrived yet. A timeout here
        isn't itself a failure — `audit_peer()` afterward still correctly
        reports real "missing final_reveal" mismatches for a peer that
        truly never sent one; this only removes the false-negative case
        where the reveal was already in flight."""
        if self._peer_final_reveal_received:
            return
        try:
            await await_with_deadline(
                self._peer_final_reveal_event.wait(), timeout_seconds=timeout_seconds
            )
        except DeadlineExceededError:
            self.trace.log("peer_final_reveal_wait_timed_out", timeout_seconds=timeout_seconds)

    async def send_final_reveal_to_peer(self, peer_url: str) -> dict:
        """Rule 18: only ever called at game end. No state-machine
        transition here — Final Reveal sits outside the per-turn cycle
        entirely (PRD 6 Design Question 4), so there is no legal per-turn
        state for a failure here to land on; a failure is logged and
        re-raised, not converted into `TECHNICAL_LOSS`.

        PRD 10: logs the nonces themselves into `self.trace` — not just
        `step_count` (below) — the moment they're revealed, *before*
        attempting the send. Rule 18 only requires secrecy *until* game
        end; this is that exact moment, and a standalone `replay --log
        <path>` run against a completed match's log file (this repo's own
        `nonces_from_log`, `observability/replay_viewer.py`) has no other
        source for them once the live process has exited. Logged
        unconditionally, not gated on the send succeeding — the self-audit
        half (`run_mutual_audit`) only needs locally-known-good data,
        never the peer's own reachability."""
        nonces = {str(step): nonce for step, nonce in self._pending_nonces.items()}
        intents = {str(step): intent for step, intent in self._pending_intents.items()}
        self.trace.log("nonces_revealed", nonces=nonces)
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
