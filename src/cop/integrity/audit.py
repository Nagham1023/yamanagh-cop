"""The end-of-game mutual audit (rule 19, **[FATAL]**: any hash mismatch is
a technical forfeit, no exceptions, no partial credit) — replays every
turn's `committing` trace entry (`orchestrator_commit_reveal.py` logs the
full envelope there except the nonce), plugs in the now-revealed nonce for
that step, recomputes `Hcommit`, and compares against what was actually
logged as broadcast at commit time.

This audits *this side's own* log against *this side's own* later-revealed
nonces — the self-consistency half of ch. 5.4's mutual audit. The other
half (comparing against the *peer's* independently-kept log) happens once
both sides' logs are available together, outside this repo's own process
(rule 1/2: no shared live state) — `run_mutual_audit` is the replay engine
either side runs over either log, not a two-log comparator itself.

Also the required home for `verify_scent_map_against_commit`
(`tests/unit/test_scent_commitment.py`/the former guard test named this
exact import path) — re-exported from `scent_commitment.py` rather than
redefined here, so the scent-map hash logic exists in exactly one place.
Not yet wired into `run_mutual_audit` itself: doing so would require this
repo's trace log to also persist each turn's full scent field (large,
already sent once over the wire) — a live full-game-loop concern PRD 6's
own "Explicitly out of scope" section defers, not silently dropped.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .commit_reveal import CommitEnvelope, commit
from .scent_commitment import verify_scent_map_against_commit

__all__ = ["AuditResult", "run_mutual_audit", "verify_scent_map_against_commit"]


@dataclass(frozen=True)
class AuditResult:
    passed: bool
    mismatches: list[dict[str, Any]] = field(default_factory=list)


def _read_trace_log(trace_log_path: str | Path) -> list[dict[str, Any]]:
    lines = Path(trace_log_path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _envelope_from_commit_entry(entry: dict[str, Any], nonce: str) -> CommitEnvelope:
    return CommitEnvelope(
        state=bytes.fromhex(entry["state"]),
        move=entry["move"],
        intent=entry["intent"],
        nonce=nonce,
        hint_text=entry["hint_text"],
        step=entry["step"],
        role=entry["role"],
    )


def run_mutual_audit(trace_log_path: str | Path, nonces: dict[int, str] | dict[str, str]) -> AuditResult:
    """Replay every `committing` entry in `trace_log_path`, keyed by step;
    for each step with a revealed nonce, recompute `Hcommit` and compare
    (`secrets.compare_digest`) against what was actually logged as
    broadcast. A step with no revealed nonce, or any hash mismatch, is a
    failure — rule 19 has no partial-credit reading.

    `nonces` keys are normalized to `int` before lookup, accepting either
    shape — `receive_final_reveal`'s own wire payload is necessarily
    string-keyed (JSON object keys are always strings), while a self-audit
    caller passing this process's own `_pending_nonces` already has int
    keys. Without this normalization, a wire-sourced `nonces` dict would
    silently fail every lookup (`"0" != 0`), reporting "no nonce revealed"
    for an honestly-revealed game — found during review, not by a failing
    test, since no caller wires the wire-sourced path yet.

    Scoped to the *most recent* `server_starting` entry onward — found
    live: a shared log path reused across many separate dev-testing
    launches (this file's own naming is per game-id/sub-game-number, not
    per-process) accumulates `committing` entries from every earlier
    match too, each with its own unrelated `h_commit` for the same step
    numbers a brand-new match starts counting from again. Auditing the
    whole file against only the *current* match's own nonces then reports
    hundreds of false "Hcommit mismatch" entries for commits this process
    never made, failing an honestly-played match's self-audit for a
    reason that has nothing to do with tampering. A real competitive
    series never hits this (`sub_game_number` changes every sub-game, so
    each one's log file is genuinely fresh) — this guards the case
    nobody's actually relying on the naming convention alone to prevent."""
    mismatches: list[dict[str, Any]] = []
    all_entries = _read_trace_log(trace_log_path)
    match_start = max(
        (entry["time"] for entry in all_entries if entry.get("event") == "server_starting"),
        default=None,
    )
    commit_entries = [
        entry
        for entry in all_entries
        if entry["event"] == "committing" and (match_start is None or entry["time"] >= match_start)
    ]
    nonces_by_step = {int(step): nonce for step, nonce in nonces.items()}

    for entry in commit_entries:
        step = entry["step"]
        nonce = nonces_by_step.get(step)
        if nonce is None:
            mismatches.append({"step": step, "reason": "no nonce revealed for this step"})
            continue
        envelope = _envelope_from_commit_entry(entry, nonce)
        recomputed = commit(envelope)
        if not secrets.compare_digest(recomputed, entry["h_commit"]):
            mismatches.append(
                {
                    "step": step,
                    "reason": "Hcommit mismatch",
                    "logged_h_commit": entry["h_commit"],
                    "recomputed_h_commit": recomputed,
                }
            )

    return AuditResult(passed=not mismatches, mismatches=mismatches)
