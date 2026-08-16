"""PRD 6's real per-turn Commit-Reveal protocol (ch. 5.3.1/5.3.2) — split
out of `orchestrator_peer.py`, which would otherwise cross the 150-line
house cap. A mixin: reaches into `self.trace`, `self.state_machine`,
`self.config`, `self.game_state`, `self._pending_nonces`/`_pending_intents`
(`Orchestrator.__init__`), plus `self._fail_to_technical_loss` (sibling
`PeerCommsMixin`), `self._call_with_connect_retry` (sibling
`ConnectRetryMixin`), and `self._claim_capture_if_warranted` (sibling
`CaptureClaimMixin`, PRD 8). `self._pending_intents` (PRD 7) gives
`send_final_reveal_to_peer` both the nonce and Intent flag the peer's own
`run_peer_audit` needs to recompute `Hcommit`.

Supersedes PRD 4's `send_to_peer` — `take_turn` (`orchestrator_turn.py`)
calls `commit_and_reveal_to_peer` now."""

from __future__ import annotations

from .domain.board import Position
from .integrity.commit_payload import canonical_state_bytes
from .integrity.commit_reveal import CommitEnvelope, commit, move_to_wire, verify
from .integrity.nonce import generate_nonce
from .planner.deadline import now_and_deadline
from .reasoning.brain_base import Action, PlaceBarrier
from .tools.mcp_client_prd6 import send_barrier_declaration, send_commit, send_reveal

_ROLE = "cop"  # rule 1/2: this repo's own role is a compile-time constant, never read from anywhere


class CommitRevealMixin:
    async def commit_and_reveal_to_peer(
        self,
        peer_url: str,
        action: Action,
        intent: bool,
        hint_text: str,
        believed_thief_pos: Position | None = None,
    ) -> dict:
        """Commit `Hcommit` (Step 1), await the peer's ack (Step 2), reveal
        `(move, hint_text)` with the nonce still hidden (Step 3, rule 18),
        await that ack, then `VERIFYING`'s own lightweight, local
        self-check: recompute `Hcommit` from the envelope and this side's
        own just-generated nonce and confirm it matches what was actually
        sent — a local bug check, not a cross-peer audit (that stays
        `integrity/audit.py`'s own job, PRD 6 Design Question 4).

        The nonce is retained (`self._pending_nonces`), never transmitted
        here — only `receive_final_reveal`, at game end, sends it (rule 18).
        The `committing` trace entry logs the *rest* of the envelope
        (everything except the nonce) even though `state`/`intent` never
        cross the wire this early — `integrity/audit.py::run_mutual_audit`
        needs the full envelope back, keyed by step. `send_commit`/
        `send_reveal` each also carry a `sent_at`/`deadline_at` pair
        (`now_and_deadline`, PRD 15, ch. 8.4)."""
        connection = self._get_peer_connection(peer_url)
        step = self.game_state.steps_taken
        nonce = generate_nonce()
        envelope = CommitEnvelope(
            state=canonical_state_bytes(self.game_state),
            move=move_to_wire(action),
            intent=intent,
            nonce=nonce,
            hint_text=hint_text,
            step=step,
            role=_ROLE,
        )
        h_commit = commit(envelope)

        self.state_machine.transition("COMMITTING")
        self.trace.log(
            "committing",
            peer_url=peer_url,
            h_commit=h_commit,
            step=step,
            state=envelope.state.hex(),
            move=envelope.move,
            intent=envelope.intent,
            hint_text=envelope.hint_text,
            role=envelope.role,
        )
        try:
            sent_at, deadline_at = now_and_deadline(self.config.response_timeout_seconds)
            await self._call_with_connect_retry(
                lambda: send_commit(connection, h_commit, sent_at, deadline_at),
                timeout_seconds=self.config.response_timeout_seconds,
            )
        except Exception as exc:
            self._fail_to_technical_loss(exc)
            raise

        self.state_machine.transition("AWAITING_REVEAL")
        try:
            sent_at, deadline_at = now_and_deadline(self.config.response_timeout_seconds)
            result = await self._call_with_connect_retry(
                lambda: send_reveal(connection, envelope.move, hint_text, sent_at, deadline_at),
                timeout_seconds=self.config.response_timeout_seconds,
            )
        except Exception as exc:
            self._fail_to_technical_loss(exc)
            raise

        if isinstance(action, PlaceBarrier):
            # Rule 15 (**[FATAL]**): openly declare every barrier placement,
            # the same turn it's placed. Rule 16 (never lying about it) is
            # enforced by `envelope.move` already carrying this same
            # placement — a mismatch at final audit is the catch, not this
            # call itself. Sent *before* the VERIFYING transition,
            # deliberately: this is still an active wait on a peer
            # response, and only AWAITING_REVEAL (not VERIFYING) has a
            # TECHNICAL_LOSS edge in the book-matching table
            # (`state_machine.py`'s own docstring) — sending it any later
            # would strand a failed call with no legal edge to fail onto.
            try:
                await self._call_with_connect_retry(
                    lambda: send_barrier_declaration(
                        connection, action.target.col, action.target.row
                    ),
                    timeout_seconds=self.config.response_timeout_seconds,
                )
            except Exception as exc:
                self._fail_to_technical_loss(exc)
                raise
            self.trace.log(
                "barrier_declared", col=action.target.col, row=action.target.row, step=step
            )

        # PRD 8, same window/reasoning as barrier declaration above (see orchestrator_capture.py).
        await self._claim_capture_if_warranted(peer_url, action, believed_thief_pos, step)

        self.state_machine.transition("VERIFYING")
        if not verify(envelope, h_commit):
            # Local bug only (final audit catches opponent dishonesty separately) — logged
            # here since VERIFYING has no TECHNICAL_LOSS edge, so nothing else would catch it.
            self.trace.log(
                "local_verify_mismatch", h_commit=h_commit, step=step, move=envelope.move
            )
            raise RuntimeError(
                f"revealed move at step {step} does not match this side's own earlier commit"
            )
        self._pending_nonces[step] = nonce
        self._pending_intents[step] = intent
        self.trace.log(
            "revealed",
            h_commit=h_commit,
            move=envelope.move,
            hint_text=hint_text,
            step=step,
            result=result,
        )

        self.state_machine.transition("WAITING_FOR_OPPONENT")
        return result
