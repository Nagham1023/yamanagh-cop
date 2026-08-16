"""PRD 7's bilateral mutual audit wiring — closes PRD 6's own "Known gap"
for real (`PRD-7-reporting-shell.md`'s Design Question 11). Split into its
own mixin file rather than growing `orchestrator_turn.py`/
`orchestrator_peer.py` further past the 150-line cap.

Records the peer's own committed-and-revealed data (`on_commit`, plus this
side's own persisted half of `on_reveal` in `orchestrator_turn.py`, plus
`on_final_reveal`) into `self.peer_trace`; sends this side's own Final
Reveal; runs the real peer-side audit. Final Reveal happens once, at game
end (ch. 5.3.2), outside the per-turn `PeerStateMachine` cycle (PRD 6
Design Question 4) — this mixin never transitions `self.state_machine`.
"""

from __future__ import annotations

from .domain.board import Position
from .integrity.audit import AuditResult
from .integrity.peer_trace import run_peer_audit
from .planner.deadline import DeadlineExceededError, await_with_deadline
from .planner.retry import retry_on_connection_failure
from .tools.mcp_client_prd6 import send_final_reveal


class PeerAuditMixin:
    def _on_final_reveal_received(self, nonces: dict, intents: dict) -> dict:
        """Server-role counterpart to `send_final_reveal_to_peer` — the
        peer's own nonces and Intent flags, both required to recompute
        their `Hcommit` (ch. 5.3.1's equation needs `Intent`, not just
        `Nonce`; `State` is never sent at all, see `peer_trace.py`).

        Ch.5.3.2 Step 4 names Final Reveal as the end-of-game step ("all
        Nonces (end of game)") — a live run showed this callback used to
        only record audit data while `play_game` kept looping to the step
        ceiling, producing contradictory winners (rule 35); the flag below
        is what stops the loop.

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

    async def _await_peer_final_reveal(self, timeout_seconds: float | None = None) -> None:
        """`report_game()`'s own real fix for the race this module's other
        docstrings describe: don't call `audit_peer()` the instant this
        side's own outcome is known, since the peer's independently-timed
        Final Reveal may genuinely not have arrived yet. A timeout here
        isn't itself a failure — `audit_peer()` afterward still correctly
        reports real "missing final_reveal" mismatches for a peer that
        truly never sent one; this only removes the false-negative case
        where the reveal was already in flight.

        Defaults to `self.config.response_timeout_seconds` (the same
        already-negotiated budget used everywhere else here), not a short,
        separate constant this file used to have — found live: a slower
        peer's own Final Reveal arrived 23s after this side had already
        given up and persisted a mutual `audit_forfeit_applied` (rule 19),
        even though her reply, once it *did* arrive, verified cleanly
        (27/27 steps) — an avoidable false forfeit. Costs the test suite
        nothing: every `report_game()` test that matters here already
        either pre-sets `_peer_final_reveal_received = True`
        (`test_orchestrator_end_of_game.py::_client`) or passes its own
        explicit `timeout_seconds` (`test_peer_final_reveal_wait.py`)."""
        if self._peer_final_reveal_received:
            return
        if timeout_seconds is None:
            timeout_seconds = self.config.response_timeout_seconds
        try:
            await await_with_deadline(
                self._peer_final_reveal_event.wait(), timeout_seconds=timeout_seconds
            )
        except DeadlineExceededError:
            self.trace.log("peer_final_reveal_wait_timed_out", timeout_seconds=timeout_seconds)

    async def send_final_reveal_to_peer(self, peer_url: str) -> dict:
        """Rule 18: only ever called at game end. No state-machine
        transition here — Final Reveal sits outside the per-turn cycle
        (PRD 6 Design Question 4), so there is no legal per-turn state for
        a failure here to land on; a failure is logged and re-raised, not
        converted into `TECHNICAL_LOSS`.

        PRD 10: logs the nonces themselves into `self.trace` — not just
        `step_count` (below) — the moment they're revealed, *before*
        attempting the send. Rule 18 only requires secrecy *until* game
        end; a standalone `replay --log <path>` run (`nonces_from_log`,
        `observability/replay_viewer.py`) has no other source for them
        once the live process has exited. Logged unconditionally, not
        gated on the send succeeding — the self-audit half
        (`run_mutual_audit`) only needs locally-known-good data, never
        the peer's own reachability.

        Retried on a connection failure (`planner/retry.py`, shared with
        `request_scent_map_from_peer`): `receive_final_reveal` is a pure
        overwrite (`PeerTrace.record_final_reveal`'s own `setdefault`), so
        a duplicate delivery after a dropped tunnel is a safe no-op on the
        receiving side — found live, the same real match whose scent-map
        pull needed this."""
        connection = self._get_peer_connection(peer_url)
        nonces = {str(step): nonce for step, nonce in self._pending_nonces.items()}
        intents = {str(step): intent for step, intent in self._pending_intents.items()}
        self.trace.log("nonces_revealed", nonces=nonces)
        try:
            result = await await_with_deadline(
                retry_on_connection_failure(
                    lambda: send_final_reveal(connection, nonces, intents),
                    attempts=self.private_config.scent_map_retry_attempts,
                    delay_seconds=self.private_config.scent_map_retry_delay_seconds,
                    on_retry=lambda attempt, exc: self.trace.log(
                        "final_reveal_send_retrying", attempt=attempt, reason=str(exc)
                    ),
                ),
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
