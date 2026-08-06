"""Orchestrator's brain-driven turn (PRD 3/4) — split out of orchestrator.py,
which grew past the 150-line house cap once this landed. A mixin, not a
standalone class: reaches into `self.state_machine`, `self.game_state`,
`self.trace`, `self.brain`, `self.board`, `self.belief_map`,
`self.scent_field`, `self.hint_provider`, `self.template_provider`,
`self.private_config`, `self._rng`, and `self.send_to_peer`, all of which
`Orchestrator.__init__`/`send_to_peer` set up — this file only exists to
keep `orchestrator.py` under the cap.
"""

from __future__ import annotations

from .reasoning.hint import (
    choose_provider,
    decide_intent,
    generate_hint,
    generate_scent_report,
    interpret_hint,
)

# Not an Appendix F parameter — Table 21 defines the provider/cadence, not a
# lying frequency. A fixed, conservative default (never lie) until a real
# deception strategy is worth building (PLAN.md's own "optional if time
# permits" framing) — the milestone forces Intent=False directly via
# reasoning.hint.decide_intent's own parameters, not through this default.
_DEFAULT_LIE_PROBABILITY = 0.0


class BrainTurnMixin:
    async def take_turn(self, peer_url: str) -> dict:
        """Client role, brain-driven: ask `self.brain` to decide, apply the
        result, update scent/belief from the cop's own move, generate and
        send a hint (rule 26/27 — no coordinates cross the wire).

        One turn only — no internal loop, no `determine_outcome` call here;
        that's `reasoning/subgame.py`'s job.

        The decide-and-apply step is wrapped the same way `send_to_peer`
        wraps its own failure path: `GameState.apply` raises on an illegal
        action (a brain bug, not an impossible event), and leaving that
        uncaught would strand the state machine in `COMPUTING_MOVE` with
        nothing logged — the same shape of gap PRD 2's `send_to_peer`
        already guards against for network failures.
        """
        self.state_machine.transition("COMPUTING_MOVE")
        try:
            action = self.brain._decide_move(
                self.game_state.own_pos,
                self.game_state.target_pos,
                self.board,
                self.game_state.barriers,
            )
            self.game_state.apply(action, self.board)
        except Exception as exc:
            self.trace.log(
                "technical_loss",
                reason=str(exc),
                exception_type=type(exc).__name__,
                state=self.state_machine.state,
            )
            self.state_machine.transition("TECHNICAL_LOSS")
            raise
        self.trace.log("computed_move", action=repr(action))

        self.scent_field.advance(self.game_state.own_pos, self.board)
        self.belief_map.update_from_scent(self.scent_field, self.game_state.own_pos, self.board)
        self.game_state.target_pos = self.belief_map.most_likely_cell()

        intent = decide_intent(_DEFAULT_LIE_PROBABILITY, self._rng)
        provider = choose_provider(
            self.game_state.steps_taken,
            self.hint_provider,
            self.template_provider,
            self.private_config.every_n_steps,
        )
        text = generate_hint(self.game_state.own_pos, provider, self.config, intent)
        sampled = self.scent_field.sample(self.game_state.own_pos, self.board)
        scent_report = generate_scent_report(sampled, self.game_state.own_pos, self.config)
        self.trace.log("hint_generated", intent=intent, steps_taken=self.game_state.steps_taken)

        return await self.send_to_peer(peer_url, text, scent_report)

    def _on_hint_received(self, text: str, scent_report: str) -> None:
        """Server-role counterpart to `take_turn`'s outgoing hint: interpret
        the peer's tactical hint (possibly a lie) and always-truthful scent
        report (Revision 1), folding both into the belief map at their own
        trust weight. Injected into `build_server` as `on_hint` rather than
        importing `reasoning.hint`/`memory.belief` there — `tools/` stays a
        thin transport layer (rule 3/I2), the Orchestrator owns wiring
        belief updates.

        Each field is gated on `hint_word_limit` independently before it
        touches belief state (rule-auditor finding, I9 — everything a peer
        sends is untrusted): `receive_hint`'s ack already flags an over-limit
        field to the sender, but the ack alone doesn't stop the *content*
        from reaching this callback. A malformed one field must not also
        block the other, still-valid field from updating belief.
        """
        if len(text.split()) <= self.config.hint_word_limit:
            focal_point = interpret_hint(text, self.board)
            self.belief_map.update_from_hint(focal_point, self.board)
        if len(scent_report.split()) <= self.config.hint_word_limit:
            scent_focal_point = interpret_hint(scent_report, self.board)
            self.belief_map.update_from_scent_report(scent_focal_point, self.board)
        self.trace.log("hint_received", text=text, scent_report=scent_report)
