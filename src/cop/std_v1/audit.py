"""Per-sub-game mutual audit and final series-consensus exchange (spec
Sections 9-11). Same mutual, idempotent-resend shape as
`handshake.py::negotiate_sub_game` — Section 9's own "both MUST be sent
promptly" and Section 10's explicit consensus-exchange steps.
"""

from __future__ import annotations

import asyncio
import time

from ..planner.deadline import DeadlineExceededError
from .sealing import verify_record
from .wire import send_audit

WIRE_ROLES = ("police", "thief")


def build_audit_envelope(sender: str, records: list[dict], result_claim: str, sub_game_number: int) -> dict:
    """The per-sub-game audit envelope this side sends."""
    return {
        "sender": sender,
        "records": records,
        "result_claim": result_claim,
        "sub_game_number": sub_game_number,
    }


def build_consensus_envelope(sender: str, consensus_sha: str) -> dict:
    """Section 10 step 3: no `sub_game_number` at all — this is what lets
    `StdExchange`'s `None`-keyed bucket route it correctly."""
    return {"sender": sender, "result_claim": "series_consensus", "records": [], "consensus_sha": consensus_sha}


async def send_and_await(
    connection,
    wait_fn,
    envelope: dict,
    resend_interval_sec: float = 2.0,
    ceiling_sec: float = 60.0,
) -> dict:
    """Shared resend-until-matched loop for both the per-sub-game audit
    and the final consensus exchange. `wait_fn(timeout)` is a plain
    (non-async) callable — `exchange.wait_for_audit`/`wait_for_consensus`
    — run via `asyncio.to_thread` here so this coroutine never blocks the
    event loop on `StdExchange`'s own polling sleep."""
    deadline = time.monotonic() + ceiling_sec
    while time.monotonic() < deadline:
        await send_audit(connection, envelope)
        remaining = deadline - time.monotonic()
        try:
            return await asyncio.to_thread(wait_fn, min(resend_interval_sec, max(0.0, remaining)))
        except DeadlineExceededError:
            continue
    raise DeadlineExceededError(f"no matching audit response within {ceiling_sec}s")


def verify_peer_records(records: list[dict], peer_commits: dict[int, str]) -> dict:
    """Re-hashes every one of the peer's revealed records and compares
    against the commit this side actually witnessed live for that step —
    never against a commit the record merely claims for itself, which
    would let a peer approve its own tampering."""
    mismatched_steps = []
    for record in records:
        step = record.get("step")
        expected_commit = peer_commits.get(step)
        if expected_commit is None or not verify_record(record, expected_commit):
            mismatched_steps.append(step)
    return {
        "log_verified": not mismatched_steps,
        "tampered": bool(mismatched_steps),
        "mismatched_steps": mismatched_steps,
    }


def build_sub_game_row(
    sub_game_number: int, result: str, roles: dict[str, str], score: dict[str, int], winner_group: str | None
) -> dict:
    """Section 11's own exactly-five-key row shape."""
    return {
        "sub_game_number": sub_game_number,
        "result": result,
        "roles": dict(roles),
        "score": dict(score),
        "winner_group": winner_group,
    }


def build_consensus_object(game_id: str, game_uid: str, sub_games: list[dict]) -> dict:
    """Section 11's own exactly-three-key top-level object, rows always
    re-sorted by ascending `sub_game_number` before returning."""
    ordered = sorted(sub_games, key=lambda row: row["sub_game_number"])
    return {"game_id": game_id, "game_uid": game_uid, "sub_games": ordered}


def validate_consensus_envelope(envelope: dict) -> str:
    """Section 10 step 3's own explicit acceptance rules. Returns the
    peer's own `consensus_sha` on success; raises `ValueError` otherwise —
    a malformed envelope here must never be silently treated as agreement."""
    if envelope.get("result_claim") != "series_consensus":
        raise ValueError("consensus envelope has the wrong result_claim")
    if envelope.get("records") != []:
        raise ValueError("consensus envelope must carry an empty records list")
    consensus_sha = envelope.get("consensus_sha")
    if not isinstance(consensus_sha, str) or len(consensus_sha) != 64 or any(
        c not in "0123456789abcdef" for c in consensus_sha
    ):
        raise ValueError("consensus envelope's consensus_sha is not 64 lowercase hex chars")
    if envelope.get("sender") not in WIRE_ROLES:
        raise ValueError(
            f"consensus envelope's sender must be a wire role {WIRE_ROLES}, got {envelope.get('sender')!r}"
        )
    return consensus_sha


def confirm_agreement(
    all_sub_games_audited_clean: bool, all_sub_game_results_agreed: bool, local_digest: str, peer_digest: str
) -> bool:
    """Section 10 step 4: agreement is confirmed only when every remote
    log verified untampered, every sub-game result was mutually agreed,
    AND the received remote digest equals the local one."""
    return all_sub_games_audited_clean and all_sub_game_results_agreed and local_digest == peer_digest
