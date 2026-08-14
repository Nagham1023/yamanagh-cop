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
from .reasoning.hint import choose_provider, decide_intent, generate_hint

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
        # Observability, not behavior: added while diagnosing a real match
        # where the cop never closed distance on the thief — without this,
        # there was no way to see whether belief was actually migrating
        # toward the real scent trail turn by turn, only where the cop's
        # own feet ended up.
        self.trace.log(
            "belief_target_updated",
            target_pos=[self.game_state.target_pos.col, self.game_state.target_pos.row],
            target_probability=self.belief_map.probability(self.game_state.target_pos),
        )

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
