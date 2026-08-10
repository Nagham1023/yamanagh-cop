"""PRD 8's first-ever live, multi-turn game loop — every prior PRD's
`take_turn()` decides and sends exactly one turn; nothing before this
called it repeatedly, checked for game-over, or knew when a match ended
(`reasoning/subgame.py::run_local_subgame` is the offline, no-network
equivalent, PRD 3's own algorithm-correctness sandbox, never the wire).

Resolves TODO8 §4's own open question, decided here rather than left
ambiguous: `take_turn()` itself raises on a technical loss (its own
`except Exception` block transitions state, then re-raises) — `play_game()`
catches that and converts it to `Outcome.TECHNICAL_LOSS`, so a caller never
needs a `try/except` to learn a match ended; an ordinary game-over and a
genuine bug are both delivered the same way, as this function's own return
value.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from .domain.end_conditions import determine_outcome
from .domain.scoring import Outcome
from .observability.live_gui import LiveGuiWindow, render_state


class GameLoopMixin:
    def _outcome_after_peer_final_reveal(self) -> Outcome:
        """Ch.5.3.2: peer Final Reveal ends the match. Prefer a capture we
        already confirmed (rules 21/22); else honour survival/ceiling if
        those local predicates already fire; never invent SURVIVAL early
        (rule 35 / rule 22)."""
        if self._last_turn_captured:
            return Outcome.CAPTURE
        outcome = determine_outcome(
            captured=False,
            steps_taken=self.game_state.steps_taken,
            step_ceiling=self.config.step_ceiling,
            survival_threshold=self.config.survival_threshold,
        )
        if outcome is not None:
            return outcome
        return Outcome.TECHNICAL_LOSS

    async def play_game(self, peer_url: str, enable_gui: bool = False) -> Outcome:
        """Loop `take_turn()` until capture, the step ceiling, the survival
        threshold, a peer Final Reveal (Ch.5.3.2), or a technical loss
        ends the match.

        PRD 10: stamps `self._match_started_at`/`_match_ended_at` (ISO-8601
        UTC) at this function's own real boundaries — the only two points
        in this repo's own lifecycle that legitimately represent "a match
        began"/"a match ended" — `report_game()`'s `DeclarationBundle`
        needs both and had no other honest source for them."""
        self._match_started_at = datetime.now(UTC).isoformat()
        gui_window = LiveGuiWindow(board_size=self.config.board_size) if enable_gui else None
        if gui_window is not None:
            # Paint immediately so the window is never blank while the first
            # take_turn awaits the peer (CLI `--gui` prefers LiveGuiSession).
            gui_window.update(
                render_state(
                    self.game_state.own_pos,
                    self.belief_map._probabilities,
                    str(self.state_machine.state),
                )
            )
        try:
            while True:
                if self._peer_final_reveal_received:
                    self._match_ended_at = datetime.now(UTC).isoformat()
                    return self._outcome_after_peer_final_reveal()
                try:
                    await self.take_turn(peer_url)
                except Exception:
                    self._match_ended_at = datetime.now(UTC).isoformat()
                    return Outcome.TECHNICAL_LOSS

                if gui_window is not None:
                    rendered = render_state(
                        self.game_state.own_pos,
                        self.belief_map._probabilities,
                        str(self.state_machine.state),
                    )
                    gui_window.update(rendered)
                    await asyncio.sleep(0.5)

                if self._peer_final_reveal_received:
                    self._match_ended_at = datetime.now(UTC).isoformat()
                    if gui_window is not None:
                        await asyncio.sleep(1.0)
                    return self._outcome_after_peer_final_reveal()

                outcome = determine_outcome(
                    captured=self._last_turn_captured,
                    steps_taken=self.game_state.steps_taken,
                    step_ceiling=self.config.step_ceiling,
                    survival_threshold=self.config.survival_threshold,
                )
                self.watchdog.heartbeat()
                if outcome is not None:
                    self._match_ended_at = datetime.now(UTC).isoformat()
                    if gui_window is not None:
                        await asyncio.sleep(1.0)
                    return outcome
        finally:
            if gui_window is not None:
                gui_window.close()
