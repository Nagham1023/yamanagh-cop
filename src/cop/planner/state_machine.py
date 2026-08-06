"""The PRD 2 state machine (rules 4, 5): a round-trip message exchange, nothing more.

Deliberately smaller than the book's own worked example (Ch.8, Fig. 11:
`WAITING_FOR_OPPONENT → COMPUTING_MOVE → COMMITTING → AWAITING_REVEAL →
VERIFYING → TECHNICAL_LOSS`) — that example bakes in Commit-Reveal, which is
PRD 6's rules (17–19), not PRD 2's. Building `COMMITTING`/`AWAITING_REVEAL`
states now, with no real commit-reveal behind them, would be a half-finished
stub (see PRD-2-fastmcp-infra.md, Design Question 2).

PRD 6 will extend `TRANSITIONS` below with commit/reveal states once
Commit-Reveal actually exists — this table is expected to grow, not a
finished design.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Transition table: each state maps to its set of legal successors. Every
# state can reach TECHNICAL_LOSS (deadline expiry or a watchdog-detected
# crash) — listed explicitly per state rather than special-cased, so the
# rejection logic in `transition` stays a single dict lookup (rule 5).
TRANSITIONS: dict[str, set[str]] = {
    "WAITING_FOR_OPPONENT": {"SENDING", "TECHNICAL_LOSS"},
    "SENDING": {"AWAITING_RESPONSE", "TECHNICAL_LOSS"},
    "AWAITING_RESPONSE": {"TURN_RESOLVED", "TECHNICAL_LOSS"},
    "TURN_RESOLVED": {"WAITING_FOR_OPPONENT", "TECHNICAL_LOSS"},
    "TECHNICAL_LOSS": set(),  # terminal state
}


@dataclass
class PeerStateMachine:
    state: str = field(default="WAITING_FOR_OPPONENT")

    def transition(self, target: str) -> str:
        """Move to `target` if legal; raise if not (rule 5: reject, don't absorb)."""
        legal = TRANSITIONS.get(self.state)
        if legal is None:
            raise ValueError(f"Unknown current state: {self.state!r}")
        if target not in legal:
            raise ValueError(f"Illegal transition: {self.state} -> {target}")
        self.state = target
        return self.state
