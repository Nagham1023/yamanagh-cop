"""PRD 16: `SubGameEntry` and `build_mutual_agreement` — split out of
`report_bundle.py` (already at 130/150 lines), which keeps the simpler,
already-correct declaration/config/log builders untouched. The series
accumulation logic that consumes these lives in `report_bundle_series.py`
(this file re-hit the cap once both landed together).

`mutual_agreement` is a locally-computed sha256 (reusing
`integrity/canonical_json.py`) plus a `confirmed` flag derived from
`self_audit_passed AND peer_audit_passed` — not a new bilateral wire
handshake (a materially larger scope, decided against; see
`PRD-16-series-result-report.md`'s "Decisions" section).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ..integrity.canonical_json import canonical_json_bytes


def winner_and_tie(group_a: str, score_a: int, group_b: str, score_b: int) -> tuple[str | None, bool]:
    if score_a == score_b:
        return None, True
    return (group_a if score_a > score_b else group_b), False


@dataclass(frozen=True)
class SubGameEntry:
    """One sub-game's own contribution to the series. `roles` is fixed, not
    derived: this repo can only ever report on games it played as cop
    (rule 1/2). `opponent_commit`/`opponent_score`/`this_tokens` come from
    real, locally-known sources; the opponent's own token consumption is
    never transmitted by any existing protocol, so it stays honestly
    `None` rather than fabricated."""

    sub_game_number: int
    this_group: str
    opponent_group: str
    started_at: str | None
    ended_at: str | None
    result: str
    this_score: int
    opponent_score: int
    this_commit: str
    opponent_commit: str | None
    this_tokens: int
    config_file: str
    log_file: str
    log_verified: bool
    peer_audit_passed: bool
    is_counted: bool

    def to_dict(self) -> dict:
        winner_group, tie = winner_and_tie(
            self.this_group, self.this_score, self.opponent_group, self.opponent_score
        )
        return {
            "sub_game_number": self.sub_game_number,
            "roles": {self.this_group: "cop", self.opponent_group: "thief"},
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "result": self.result,
            "winner_group": winner_group,
            "tie": tie,
            "github_commit": {self.this_group: self.this_commit, self.opponent_group: self.opponent_commit},
            "tokens": {self.this_group: self.this_tokens, self.opponent_group: None},
            "score": {self.this_group: self.this_score, self.opponent_group: self.opponent_score},
            "log_files": {"config": self.config_file, "log": self.log_file},
            "audit": {
                "log_verified": self.log_verified,
                "peer_audit_passed": self.peer_audit_passed,
                "tampered": not (self.log_verified and self.peer_audit_passed),
            },
            "is_counted": self.is_counted,
        }


def build_mutual_agreement(
    payload_without_agreement: dict, *, self_audit_passed: bool, peer_audit_passed: bool
) -> dict:
    """A real, verifiable seal — a lecturer can recompute this exact hash
    over the received JSON. `confirmed` is this side's own honest
    assessment (both audits passed), not a bilateral handshake result."""
    digest = hashlib.sha256(canonical_json_bytes(payload_without_agreement)).hexdigest()
    return {"sha256": digest, "confirmed": self_audit_passed and peer_audit_passed}
