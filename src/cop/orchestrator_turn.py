"""Orchestrator's brain-driven turn (PRD 3/4) — split out of orchestrator.py,
which grew past the 150-line house cap once this landed. A mixin, not a
standalone class: reaches into `self`'s `state_machine`/`game_state`/
`trace`/`brain`/`board`/`belief_map`/`scent_field`/`hint_provider`/
`template_provider`/`private_config`/`_rng`, all set up by
`Orchestrator.__init__`/`orchestrator_peer.py`/`orchestrator_commit_reveal.py`.
"""

from __future__ import annotations

import asyncio

from .planner.deadline import await_with_deadline
from .reasoning.brain_base import Action
from .reasoning.hint import choose_provider, decide_intent, generate_hint, interpret_hint

# Not an Appendix F parameter — Table 21 defines the provider/cadence, not a
# lying frequency. A fixed, conservative default (never lie) until a real
# deception strategy is worth building (PLAN.md's own "optional if time
# permits" framing) — the milestone forces Intent=False directly via
# reasoning.hint.decide_intent's own parameters, not through this default.
_DEFAULT_LIE_PROBABILITY = 0.0


class BrainTurnMixin:
    async def take_turn(self, peer_url: str | None = None) -> dict:
        """Client role, brain-driven: gather the peer's own scent map, ask
        `self.brain` to decide, apply the result, update scent/belief from
        the cop's own move, generate a hint, then commit and reveal the
        whole turn to the peer (rule 17/18/19 — Commit-Reveal over SHA-256;
        rule 26/27 — no coordinates cross the wire, ever).

        `peer_url` defaults to `self.private_config.opponent_url` — still
        overridable explicitly, which is all tests need.

        PRD 4 "Revision 3": the peer's scent map is pulled via a dedicated
        Tool call *before* deciding the move — ch. 6.5's own "gather data
        via Tool, then build [on it]" ordering — and folded into belief
        immediately.

        One turn only — no internal loop, no `determine_outcome` call here;
        that's `reasoning/subgame.py`'s job. `_decide_and_apply_move` is
        wrapped the same way `commit_and_reveal_to_peer` wraps its own
        failure path: an illegal action or a stuck/slow brain both raise,
        and leaving either uncaught would strand the state machine in
        `COMPUTING_MOVE` with nothing logged.
        """
        if peer_url is None:
            peer_url = self.private_config.opponent_url

        self.state_machine.transition("COMPUTING_MOVE")
        peer_scent_map = await self.request_scent_map_from_peer(peer_url)
        self.belief_map.update_from_scent_map(peer_scent_map, self.board)

        try:
            action = await self._decide_and_apply_move()
        except Exception as exc:
            self.trace.log(
                "technical_loss",
                reason=str(exc),
                exception_type=type(exc).__name__,
                state=self.state_machine.state,
            )
            self.state_machine.transition("TECHNICAL_LOSS")
            raise
        # PRD 8: captured before target_pos is overwritten below with next
        # turn's belief — this is the cell the brain used to decide this move.
        believed_thief_pos = self.game_state.target_pos
        self.trace.log("computed_move", action=repr(action))
        self.belief_map.zero_out_barriers(self.game_state.barriers)

        self.scent_field.advance(self.game_state.own_pos, self.board)
        self.belief_map.update_from_scent(self.scent_field, self.game_state.own_pos, self.board)
        self.game_state.target_pos = self.belief_map.most_likely_cell()

        intent, text = self._generate_and_log_hint()
        return await self.commit_and_reveal_to_peer(
            peer_url, action, intent, text, believed_thief_pos
        )

    async def _decide_and_apply_move(self) -> Action:
        """Brain decision in a worker thread, bounded by
        `response_timeout_seconds` — reused rather than a new config field,
        since Appendix F has no separate compute-time budget (`README.md`'s
        note). A stuck/slow brain now raises `DeadlineExceededError`
        (caught by `take_turn`'s own `except Exception`) instead of
        blocking the whole process forever."""
        action = await await_with_deadline(
            asyncio.get_running_loop().run_in_executor(
                None,
                self.brain._decide_move,
                self.game_state.own_pos,
                self.game_state.target_pos,
                self.board,
                self.game_state.barriers,
            ),
            timeout_seconds=self.config.response_timeout_seconds,
        )
        self.game_state.apply(action, self.board)
        return action

    def _generate_and_log_hint(self) -> tuple[bool, str]:
        """Decide Intent, pick this step's provider, generate the outgoing
        hint, and log the cost event — split out of `take_turn` once this
        file re-hit the cap. `tokens_used=0` is honest: the only implemented
        providers (`template`/`ollama`, Table 21) really do cost zero."""
        intent = decide_intent(_DEFAULT_LIE_PROBABILITY, self._rng)
        provider = choose_provider(
            self.game_state.steps_taken,
            self.hint_provider,
            self.template_provider,
            self.private_config.every_n_steps,
        )
        text = generate_hint(self.game_state.own_pos, provider, self.config, intent)
        self.trace.log(
            "hint_generated", intent=intent, steps_taken=self.game_state.steps_taken, tokens_used=0
        )
        return intent, text

    def _on_reveal_received(
        self, move: dict, hint_text: str, sent_at: float | None = None, deadline_at: float | None = None
    ) -> None:
        """Server-role counterpart to `take_turn`'s outgoing reveal:
        interpret the peer's tactical hint (possibly a lie), folding it into
        the belief map. Injected into `build_server` as `on_reveal` rather
        than importing `reasoning.hint`/`memory.belief` there — `tools/`
        stays a thin transport layer (rule 3/I2).

        `move` is an unverified claim until Final Reveal (PRD 6 DQ2) — not
        cryptographically checkable yet, since the nonce needed to recompute
        the peer's `Hcommit` doesn't exist until then; it's persisted into
        `self.peer_trace` (closing PRD 6's own "Known gap") for
        `run_peer_audit`'s later use, but never fed into belief here — only
        `hint_text` does that, and only after passing `hint_word_limit`
        (I9 — everything a peer sends is untrusted).

        Also mirrors `hint_text` into `self._last_hint_received` for the
        live GUI (PRD 7 round-2), and logs the peer's declared `sent_at`/
        `deadline_at` (PRD 15, optional, `None` for an older client) —
        observational only, never trusted (rule 9; see
        `_log_if_peer_deadline_already_expired`, `orchestrator_peer_audit.py`)."""
        self._last_hint_received = hint_text
        self.peer_trace.record_reveal(move, hint_text)
        if len(hint_text.split()) <= self.config.hint_word_limit:
            focal_point = interpret_hint(hint_text, self.board)
            self.belief_map.update_from_hint(focal_point, self.board)
        self.trace.log(
            "hint_received", text=hint_text, peer_sent_at=sent_at, peer_deadline_at=deadline_at
        )
        self._log_if_peer_deadline_already_expired(deadline_at)
