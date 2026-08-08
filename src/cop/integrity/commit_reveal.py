"""The book's own `commit()`/`verify()` pair (ch. 5.3.1, p.53's worked
code), extended to this repo's real 7-field envelope rather than the
illustrative 4-field `SHA256(State‖Move‖Intent‖Nonce)` equation — the
reference implementation's actually-signed record (p.51) also carries the
verbal hint text, an intent classification, the step number, and the role.
See `PRD-6-security-and-cryptography.md`'s Design Question 1 for the full
citation trail.

`CommitEnvelope.state` is already-canonicalized bytes from
`commit_payload.canonical_state_bytes` — this module builds on that rather
than re-deriving it (PRD 6's own "don't reopen the frozen spec" rule).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from ..domain.board import Position
from ..reasoning.brain_base import Action, Move, PlaceBarrier
from .canonical_json import canonical_json_bytes


@dataclass(frozen=True)
class CommitEnvelope:
    state: bytes
    move: dict
    intent: bool
    nonce: str
    hint_text: str
    step: int
    role: str


def move_to_wire(action: Action) -> dict:
    """`Action` (a `Move` or a `PlaceBarrier`, `reasoning/brain_base.py`) has
    no JSON-safe shape of its own — this is the one, canonical translation,
    so every caller building a `CommitEnvelope` agrees on it rather than
    each inventing its own dict shape."""
    match action:
        case Move(direction=direction):
            return {"type": "move", "direction": direction}
        case PlaceBarrier(target=target):
            return {"type": "place_barrier", "col": target.col, "row": target.row}
    raise TypeError(f"not a recognized Action: {action!r}")  # pragma: no cover — exhaustive match


def wire_to_action(move: dict) -> Action:
    """The inverse of `move_to_wire` — needed by `integrity/peer_trace.py`
    to replay a peer's own revealed `Move` sequence and reconstruct their
    `State` locally (never transmitted as a position claim, rule 27).
    Untrusted input (rule 9): raises `ValueError`, this project's own
    convention for "present but nonsensical," on a malformed shape rather
    than letting a `KeyError`/`TypeError` surface from deep inside the
    replay logic."""
    move_type = move.get("type")
    if move_type == "move":
        direction = move.get("direction")
        if not isinstance(direction, str):
            raise ValueError(f"malformed move wire payload: {move!r}")
        return Move(direction=direction)
    if move_type == "place_barrier":
        col, row = move.get("col"), move.get("row")
        if not isinstance(col, int) or not isinstance(row, int):
            raise ValueError(f"malformed place_barrier wire payload: {move!r}")
        return PlaceBarrier(target=Position(col, row))
    raise ValueError(f"unrecognized move wire payload: {move!r}")


def _canonical_envelope_bytes(envelope: CommitEnvelope) -> bytes:
    """The flat 7-key dict PRD 6 settles on (Design Question 1) — `state` is
    embedded as an already-canonical JSON *string*, not re-parsed, so
    `canonical_state_bytes`'s own byte-for-byte guarantee survives intact
    end-to-end rather than being re-serialized through a second encoder."""
    payload = {
        "state": envelope.state.decode("utf-8"),
        "move": envelope.move,
        "intent": envelope.intent,
        "nonce": envelope.nonce,
        "hint_text": envelope.hint_text,
        "step": envelope.step,
        "role": envelope.role,
    }
    return canonical_json_bytes(payload)


def commit(envelope: CommitEnvelope) -> str:
    """`Hcommit` — matches ch. 5.3.1's own worked `commit()` shape (p.53),
    built on this repo's real 7-field envelope rather than the illustrative
    4-field one."""
    return hashlib.sha256(_canonical_envelope_bytes(envelope)).hexdigest()


def verify(envelope: CommitEnvelope, h_commit: str) -> bool:
    """Recomputes and compares via `secrets.compare_digest`, never `==` —
    same primitive as p.53's own `verify()`; a plain `==` short-circuits on
    the first differing byte, a timing side-channel a `Hcommit` comparison
    should never carry."""
    return secrets.compare_digest(commit(envelope), h_commit)
