"""Turn-payload construction and commit/reveal sealing for std_v1 (spec
Section 9). The wire's own turn message has no `move` field at all — a
move is part of the hidden committed payload, revealed only at audit
(Section 10) via `submit_audit`'s own `records` list — so every payload
here is split into `_PUBLIC_FIELDS` (sent live, inside the turn message)
and `_HIDDEN_FIELDS` (only ever hashed into `commit`, revealed later as
an audit record). Mirrors `thief_peer.interop.std_v1.sealing` field for
field, so the two sides' commit hashes are computed over identical shapes.
"""

from __future__ import annotations

from .crypto import commit_of, fresh_nonce

_PUBLIC_FIELDS = (
    "step", "sender", "hint", "smell_grid",
    "barrier_placed", "capture_claim", "claim_response", "win_claim",
)
_HIDDEN_FIELDS = ("move",)


def build_turn_payload(
    step: int,
    sender: str,
    move: str,
    hint: str,
    smell_grid: dict,
    barrier_placed: list[int] | None = None,
    capture_claim: list[int] | None = None,
    claim_response: dict | None = None,
    win_claim: dict | None = None,
) -> dict:
    """Assembles the full payload (public + hidden fields together) that
    gets hashed for the commit — never sent over the wire as-is."""
    return {
        "step": step,
        "sender": sender,
        "move": move,
        "hint": hint,
        "smell_grid": smell_grid,
        "barrier_placed": barrier_placed,
        "capture_claim": capture_claim,
        "claim_response": claim_response,
        "win_claim": win_claim,
    }


def seal_turn(payload: dict) -> dict:
    """Commits to `payload` with a fresh nonce; returns `{"commit",
    "nonce"}` — the nonce must be kept locally until audit time (rule 18),
    never sent alongside the live turn message."""
    nonce = fresh_nonce()
    return {"commit": commit_of(payload, nonce), "nonce": nonce}


def build_turn_message(payload: dict, commit: str) -> dict:
    """The actual `receive_turn` wire shape: every public field, plus
    `commit` — `move` (and any other hidden field) is never present."""
    message = {key: payload[key] for key in _PUBLIC_FIELDS}
    message["commit"] = commit
    return message


def build_audit_record(payload: dict, nonce: str) -> dict:
    """The revealed record sent inside a `submit_audit` envelope — every
    field (public and hidden alike) plus the nonce, so the peer can
    re-derive `commit_of(payload, nonce)` and compare."""
    record = {key: payload[key] for key in _PUBLIC_FIELDS + _HIDDEN_FIELDS}
    record["nonce"] = nonce
    return record


def verify_record(record: dict, expected_commit: str) -> bool:
    """True if `record` (a revealed audit record) re-hashes to
    `expected_commit` — the commit this side actually witnessed live for
    that step, never a commit the record merely claims for itself."""
    payload = {key: record[key] for key in _PUBLIC_FIELDS + _HIDDEN_FIELDS}
    nonce = record["nonce"]
    return commit_of(payload, nonce) == expected_commit
