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

from .domain.end_conditions import determine_outcome
from .domain.scoring import Outcome


class GameLoopMixin:
    async def play_game(self, peer_url: str) -> Outcome:
        """Loop `take_turn()` until capture, the step ceiling, the survival
        threshold, or a technical loss ends the match."""
        while True:
            try:
                await self.take_turn(peer_url)
            except Exception:
                return Outcome.TECHNICAL_LOSS

            outcome = determine_outcome(
                captured=self._last_turn_captured,
                steps_taken=self.game_state.steps_taken,
                step_ceiling=self.config.step_ceiling,
                survival_threshold=self.config.survival_threshold,
            )
            self.watchdog.heartbeat()
            if outcome is not None:
                return outcome
