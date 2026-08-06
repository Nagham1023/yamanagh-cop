"""Orchestrator's brain-driven turn (PRD 3) — split out of orchestrator.py,
which grew past the 150-line house cap once this landed. A mixin, not a
standalone class: `take_turn` reaches into `self.state_machine`,
`self.game_state`, `self.trace`, `self.brain`, `self.board`, and
`self.send_to_peer`, all of which `Orchestrator.__init__`/`send_to_peer`
set up — this file only exists to keep `orchestrator.py` under the cap.
"""

from __future__ import annotations


class BrainTurnMixin:
    async def take_turn(self, peer_url: str) -> dict:
        """Client role, brain-driven: ask `self.brain` to decide, apply the
        result to `self.game_state`, send the resulting position.

        One turn only — no internal loop, no `determine_outcome` call here;
        that's `reasoning/subgame.py`'s job. Sends `game_state.own_pos`
        after applying the action regardless of whether it was a move or a
        barrier placement: a barrier turn leaves `own_pos` unchanged (the
        forgo-move rule), so this is still an accurate position announcement
        either way — no separate barrier-announcement wire message exists
        yet (rule 15/16 truthful declaration is PRD 6's job).

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
        return await self.send_to_peer(
            peer_url, col=self.game_state.own_pos.col, row=self.game_state.own_pos.row
        )
