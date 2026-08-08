"""The genuinely bilateral half of the mutual audit (rule 36, ch. 5.4) —
closes PRD 6's own "Known gap": each side reconstructs and verifies the
**peer's** own committed-and-revealed data, not a self-check
(`integrity/audit.py::run_mutual_audit` is the self-audit half).

`PeerTrace` persists the peer's `h_commit` (`on_commit`), `(move, hint_text)`
(`on_reveal`), and `(nonce, intent)` (`on_final_reveal`) — structurally
parallel to this side's own `committing`/`revealed` trace entries, keyed by
step. Commit and reveal calls are assumed to arrive in the peer's own
strict per-turn order (their `commit_and_reveal_to_peer` sends commit then
awaits its ack before sending reveal, every turn) — an internal counter,
not a step number carried over the wire, since `receive_commit`/
`receive_reveal` carry none (rule 27: nothing here is a position claim, and
a step counter isn't one either, but keeping the wire minimal was PRD 6's
own choice throughout). Starts at `1`, not `0`: `GameState.apply()` always
increments `steps_taken` *before* `commit_and_reveal_to_peer` reads it
(`orchestrator_turn.py::take_turn`'s own ordering), so the peer's own
first-ever committed step is always `1` — the counter here has to match
that exactly, or every step lands off by one against the nonces/intents
`receive_final_reveal` later delivers (which *are* keyed by the peer's own
real `steps_taken`, via `_pending_nonces`/`_pending_intents`).

`State` is never transmitted at all — `run_peer_audit` reconstructs it by
replaying the peer's own revealed `Move` sequence from their publicly known
start position (part of the shared, locked config both sides already
have), the same derivation `PRD-7-reporting-shell.md`'s Design Question 11
describes.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..reasoning.state import GameState, ground_truth_target_position
from .audit import AuditResult
from .commit_payload import canonical_state_bytes
from .commit_reveal import CommitEnvelope, commit, wire_to_action


@dataclass
class PeerTraceEntry:
    h_commit: str | None = None
    move: dict | None = None
    hint_text: str | None = None
    nonce: str | None = None
    intent: bool | None = None


class PeerTrace:
    def __init__(self) -> None:
        self._entries: dict[int, PeerTraceEntry] = {}
        self._next_commit_step = 1
        self._next_reveal_step = 1

    def record_commit(self, h_commit: str) -> int:
        step = self._next_commit_step
        self._entries.setdefault(step, PeerTraceEntry()).h_commit = h_commit
        self._next_commit_step += 1
        return step

    def record_reveal(self, move: dict, hint_text: str) -> int:
        step = self._next_reveal_step
        entry = self._entries.setdefault(step, PeerTraceEntry())
        entry.move = move
        entry.hint_text = hint_text
        self._next_reveal_step += 1
        return step

    def record_final_reveal(self, nonces: dict[str, str], intents: dict[str, bool]) -> None:
        for step_str, nonce in nonces.items():
            self._entries.setdefault(int(step_str), PeerTraceEntry()).nonce = nonce
        for step_str, intent in intents.items():
            self._entries.setdefault(int(step_str), PeerTraceEntry()).intent = intent

    @property
    def entries(self) -> dict[int, PeerTraceEntry]:
        return dict(self._entries)  # defensive copy — callers can't mutate our own state


def run_peer_audit(
    peer_trace: PeerTrace, peer_start: Position, board: Board, barrier_quota: int, role: str = "thief"
) -> AuditResult:
    """Replays the peer's own revealed moves from `peer_start` to
    reconstruct `State` at each step, then recomputes and compares
    `Hcommit` against what the peer actually committed to — the real,
    cross-peer half of rule 19/36, not a self-consistency check."""
    mismatches: list[dict[str, Any]] = []
    # target_pos is never read by this reconstruction (only own_pos/steps_taken/
    # barriers feed canonical_state_bytes) — routed through the PRD 4 seam
    # function anyway so this stays honestly neither "ground truth" nor
    # "belief-driven" for `test_prd4_seam.py`'s own exhaustive guard.
    game_state = GameState(
        own_pos=peer_start,
        target_pos=ground_truth_target_position(peer_start),
        barriers=BarrierSet(quota=barrier_quota),
    )

    for step in sorted(peer_trace.entries):
        entry = peer_trace.entries[step]
        missing = [
            name
            for name, value in (
                ("commit", entry.h_commit),
                ("reveal", entry.move),
                ("final_reveal", entry.nonce),
            )
            if value is None
        ]
        if missing:
            mismatches.append({"step": step, "reason": f"missing {', '.join(missing)} for this step"})
            continue

        try:
            action = wire_to_action(entry.move)
            game_state.apply(action, board)
        except ValueError as exc:
            mismatches.append({"step": step, "reason": f"malformed or illegal move: {exc}"})
            continue

        envelope = CommitEnvelope(
            state=canonical_state_bytes(game_state),
            move=entry.move,
            intent=bool(entry.intent),
            nonce=entry.nonce,
            hint_text=entry.hint_text or "",
            step=step,
            role=role,
        )
        recomputed = commit(envelope)
        if not secrets.compare_digest(recomputed, entry.h_commit):
            mismatches.append(
                {
                    "step": step,
                    "reason": "Hcommit mismatch",
                    "logged_h_commit": entry.h_commit,
                    "recomputed_h_commit": recomputed,
                }
            )

    return AuditResult(passed=not mismatches, mismatches=mismatches)
