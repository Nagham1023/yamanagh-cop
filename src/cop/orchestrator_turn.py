"""Orchestrator's brain-driven turn (PRD 3/4) — split out of orchestrator.py,
which grew past the 150-line house cap once this landed. A mixin, not a
standalone class: reaches into `self.state_machine`, `self.game_state`,
`self.trace`, `self.brain`, `self.board`, `self.belief_map`,
`self.scent_field`, `self.hint_provider`, `self.template_provider`,
`self.private_config`, `self._rng`, `self.commit_and_reveal_to_peer`, and
`self.request_scent_map_from_peer`, all of which `Orchestrator.__init__`/
`orchestrator_peer.py`/`orchestrator_commit_reveal.py` set up — this file
only exists to keep `orchestrator.py` under the cap.
"""

from __future__ import annotations

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

        `peer_url` defaults to `self.private_config.opponent_url`
        (`[network]` in `config/game.toml`, todoFullFix.md §B3) — the
        book's own home for "the only thing I know about the opponent".
        Still overridable explicitly, which is all tests need: passing a
        `peer_url` never touches the private config file at all.

        PRD 4 "Revision 3" (`todoFullFix.md` §C4): the peer's scent map is
        pulled via a dedicated Tool call *before* deciding the move — ch.
        6.5's own "gather data via Tool, then build [on it]" ordering — and
        folded into belief immediately, so this turn's own move decision
        already reflects it, not just the next one. `RULE-19-SCENT-AUDIT-
        AT-PRD-6` closed at PRD 6: the peer's own `_get_and_commit_scent_field`
        (`orchestrator_peer.py`) logs a commitment hash at share time, and
        `integrity/audit.py::verify_scent_map_against_commit` catches a
        tampered field against it at final audit — no longer honest-by-
        construction alone.

        One turn only — no internal loop, no `determine_outcome` call here;
        that's `reasoning/subgame.py`'s job.

        The decide-and-apply step is wrapped the same way
        `commit_and_reveal_to_peer` wraps its own failure path:
        `GameState.apply` raises on an illegal action (a brain bug, not an
        impossible event), and leaving that uncaught would strand the state
        machine in `COMPUTING_MOVE` with nothing logged — the same shape of
        gap PRD 2's network calls already guard against.
        """
        if peer_url is None:
            peer_url = self.private_config.opponent_url

        self.state_machine.transition("COMPUTING_MOVE")
        peer_scent_map = await self.request_scent_map_from_peer(peer_url)
        self.belief_map.update_from_scent_map(peer_scent_map, self.board)

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
        self.belief_map.zero_out_barriers(self.game_state.barriers)

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
        self.trace.log("hint_generated", intent=intent, steps_taken=self.game_state.steps_taken)

        return await self.commit_and_reveal_to_peer(peer_url, action, intent, text)

    def _on_reveal_received(self, move: dict, hint_text: str) -> None:
        """Server-role counterpart to `take_turn`'s outgoing reveal:
        interpret the peer's tactical hint (possibly a lie), folding it into
        the belief map. Injected into `build_server` as `on_reveal` rather
        than importing `reasoning.hint`/`memory.belief` there — `tools/`
        stays a thin transport layer (rule 3/I2), the Orchestrator owns
        wiring belief updates.

        `move` (the peer's own claimed action) is an unverified claim until
        Final Reveal (PRD 6 Design Question 2) — not cryptographically
        checkable yet, since the nonce needed to recompute the peer's
        `Hcommit` doesn't exist until then. This repo doesn't fold it into
        belief here (an optional, non-required claim-based second tracker,
        flagged but explicitly out of scope in PRD 6's own Design Question
        2) — only `hint_text` feeds the belief map, same as PRD 4/5.

        Gated on `hint_word_limit` before it touches belief state
        (rule-auditor finding, I9 — everything a peer sends is untrusted):
        `receive_reveal`'s ack already flags an over-limit hint to the
        sender, but the ack alone doesn't stop the *content* from reaching
        this callback.
        """
        del move  # unverified claim (DQ2) — not consumed here, see docstring
        if len(hint_text.split()) <= self.config.hint_word_limit:
            focal_point = interpret_hint(hint_text, self.board)
            self.belief_map.update_from_hint(focal_point, self.board)
        self.trace.log("hint_received", text=hint_text)
