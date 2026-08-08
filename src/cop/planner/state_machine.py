"""PRD 6's real Commit-Reveal state machine (rules 4, 5, 17-19) — the book's
own worked example, Ch.8 Fig. 11 (p.79-80), verbatim:

    WAITING_FOR_OPPONENT -> COMPUTING_MOVE -> COMMITTING -> AWAITING_REVEAL
    -> VERIFYING -> WAITING_FOR_OPPONENT (cyclic), with TECHNICAL_LOSS as
    the one terminal state.

`COMMITTING`/`AWAITING_REVEAL`/`VERIFYING` used to be named `SENDING`/
`AWAITING_RESPONSE`/`TURN_RESOLVED` — placeholder names from PRD 2/3, before
Commit-Reveal existed to give them real content (see
PRD-2-fastmcp-infra.md, Design Question 2). Renamed here to match the
book's own vocabulary once PRD 6 built what they actually do:
`COMMITTING` sends `Hcommit`, `AWAITING_REVEAL` waits for the peer's Step-3
reveal, `VERIFYING` runs the lightweight, per-turn structural check
(`PRD-6-security-and-cryptography.md`'s Design Question 4) — reveal
arrived, well-formed, claimed move locally legal. It is **not** the full
cryptographic audit: the nonce needed to recompute `Hcommit` isn't
available until Final Reveal (rule 18), so that full check stays a
separate, one-time `integrity/audit.py::run_mutual_audit` call at game
end, outside this per-turn cycle entirely.

`NEGOTIATING` (PRD 9) is the ch. 5.5 Step-0 ceremony — logically the very
first state, before the per-turn cycle above ever starts. It is *not* the
dataclass's own default (`WAITING_FOR_OPPONENT` stays that, unchanged, so
every one of PRD 1-8's existing `PeerStateMachine()`/`Orchestrator()`
call sites and tests keeps constructing a machine already sitting at the
per-turn cycle's own resting state, exactly as before) — `negotiate_step0`
(`orchestrator_step0.py`) explicitly constructs
`PeerStateMachine(state="NEGOTIATING")` itself, the one caller that
actually runs the ceremony. `NEGOTIATING -> WAITING_FOR_OPPONENT` on a
verified match, `NEGOTIATING -> TECHNICAL_LOSS` on a hash mismatch or a
network failure — the same "a call that can hang or fail gets the edge"
reasoning `COMMITTING`'s own addition already established.

`TECHNICAL_LOSS` reachability deliberately does **not** match the book's
own diagram caption ("dashed arrows... emergency exits from a
communication step that failed") verbatim — the caption and the book's own
code table (p.80) disagree with each other: the caption implies every
state can fail out, the table wires only two. This module takes the
narrower, literal table and adds exactly one edge beyond it,
`COMMITTING -> TECHNICAL_LOSS` (a send that can itself hang or fail, same
risk shape as `COMPUTING_MOVE`'s and `AWAITING_REVEAL`'s own edges) — not a
blanket "every state reaches it." `VERIFYING` and `WAITING_FOR_OPPONENT`
get no such edge, matching the book's own table exactly: neither
represents an active wait on a pending peer response once the reveal is
already in hand (`VERIFYING`) or a specific pending response at all
(`WAITING_FOR_OPPONENT`, idle between turns). Rules 6/7 (deadline-tracking/
watchdog protection for any wait on the opponent) are independently
satisfied by the two edges the book itself already provides plus this
one addition — see PRD 6's Design Question 4 for the full argument.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Transition table: each state maps to its set of legal successors (rule 5:
# reject an illegal one, don't absorb it). See the module docstring above
# for exactly which states reach TECHNICAL_LOSS and why that set is
# narrower than "every state."
TRANSITIONS: dict[str, set[str]] = {
    "NEGOTIATING": {"WAITING_FOR_OPPONENT", "TECHNICAL_LOSS"},
    "WAITING_FOR_OPPONENT": {"COMPUTING_MOVE"},
    "COMPUTING_MOVE": {"COMMITTING", "TECHNICAL_LOSS"},
    "COMMITTING": {"AWAITING_REVEAL", "TECHNICAL_LOSS"},
    "AWAITING_REVEAL": {"VERIFYING", "TECHNICAL_LOSS"},
    "VERIFYING": {"WAITING_FOR_OPPONENT"},
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
