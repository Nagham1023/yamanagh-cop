"""PRD 6's real per-turn Commit-Reveal protocol (ch. 5.3.1/5.3.2) — split
out of `orchestrator_peer.py`, which would otherwise cross the 150-line
house cap once this landed alongside the PRD 4/5 scent-map/connection
machinery. A mixin, not a standalone class: reaches into `self.trace`,
`self.state_machine`, `self.config`, `self.game_state`, `self._pending_nonces`,
and `self._pending_intents` (all set up by `Orchestrator.__init__`), plus
`self._fail_to_technical_loss` from the sibling `PeerCommsMixin`.
`self._pending_intents` is PRD 7's own addition — `send_final_reveal_to_peer`
(`orchestrator_peer_audit.py`) needs both the nonce and the Intent flag for
this side's own committed envelope to let the peer's own `run_peer_audit`
recompute `Hcommit` (ch. 5.3.1's equation needs `Intent`, not just `Nonce`).

Supersedes PRD 4's `send_to_peer` (a bare, uncommitted hint) — `take_turn`
(`orchestrator_turn.py`) calls `commit_and_reveal_to_peer` now.
"""

from __future__ import annotations

from .integrity.commit_payload import canonical_state_bytes
from .integrity.commit_reveal import CommitEnvelope, commit, move_to_wire, verify
from .integrity.nonce import generate_nonce
from .planner.deadline import await_with_deadline
from .reasoning.brain_base import Action, PlaceBarrier
from .tools.mcp_client_prd6 import send_barrier_declaration, send_commit, send_reveal

_ROLE = "cop"  # rule 1/2: this repo's own role is a compile-time constant, never read from anywhere


class CommitRevealMixin:
    async def commit_and_reveal_to_peer(
        self, peer_url: str, action: Action, intent: bool, hint_text: str
    ) -> dict:
        """Commit `Hcommit` (Step 1), await the peer's ack (Step 2), reveal
        `(move, hint_text)` with the nonce still hidden (Step 3, rule 18),
        await that ack, then `VERIFYING`'s own lightweight, local
        self-check: recompute `Hcommit` from the envelope and this side's
        own just-generated nonce (never the peer's, which this side never
        has until Final Reveal) and confirm it matches what was actually
        sent — catching a local bug where the committed and revealed data
        diverged, not a cross-peer audit (that stays `integrity/audit.py`'s
        own separate, end-of-game job, PRD 6 Design Question 4).

        The nonce is retained (`self._pending_nonces`), never transmitted
        here — only `receive_final_reveal`, at game end, sends it (rule 18).
        The `committing` trace entry logs the *rest* of the envelope
        (`state`, `move`, `intent`, `hint_text`, `role` — everything except
        the nonce) even though `state`/`intent` never cross the wire this
        early — this is this process's own local log file, not the wire
        rule 18 governs, and `integrity/audit.py::run_mutual_audit` needs
        the full envelope back, keyed by step, to recompute `Hcommit` once
        nonces are finally available.
        """
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
            await await_with_deadline(
                send_commit(peer_url, h_commit),
                timeout_seconds=self.config.response_timeout_seconds,
            )
        except Exception as exc:
            self._fail_to_technical_loss(exc)
            raise

        self.state_machine.transition("AWAITING_REVEAL")
        try:
            result = await await_with_deadline(
                send_reveal(peer_url, envelope.move, hint_text),
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
                await await_with_deadline(
                    send_barrier_declaration(peer_url, action.target.col, action.target.row),
                    timeout_seconds=self.config.response_timeout_seconds,
                )
            except Exception as exc:
                self._fail_to_technical_loss(exc)
                raise
            self.trace.log(
                "barrier_declared", col=action.target.col, row=action.target.row, step=step
            )

        self.state_machine.transition("VERIFYING")
        if not verify(envelope, h_commit):
            # Only reachable if this process's own committed and revealed
            # data diverged between the two calls above — a local bug, not
            # an opponent's dishonesty (which final audit catches instead).
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
