"""Section-11 row construction for one finished (or timed-out) sub-game --
split out of `series_sub_game.py` once that file hit the 150-line house
cap. Nothing here talks to the network; it only turns an already-known
outcome into the row/report/meta shapes the rest of std_v1 consumes.
"""

from __future__ import annotations

from ..shared.config import GameConfig
from .audit import build_sub_game_row
from .roles import opposite_role


def _score_table(config: GameConfig) -> dict[str, dict[str, int]]:
    """Section 6's point table. The four non-zero cells are the same
    negotiated values `GameConfig`/PARAMETERS.md already lock (I6) — no
    second, hardcoded copy. The three zeroed outcomes have no dedicated
    config field; `0` there is the rule itself (Table 17: "technical
    loss: 0 to both sides, no exceptions"), the same convention
    `domain/scoring.py::score_outcome` already uses, not a magic number."""
    return {
        "capture": {"police": config.score_capture_cop, "thief": config.score_capture_thief},
        "survival": {"police": config.score_survival_cop, "thief": config.score_survival_thief},
        "timeout": {"police": 0, "thief": 0},
        "technical_loss": {"police": 0, "thief": 0},
        "tamper_forfeit": {"police": 0, "thief": 0},
    }


def _row_for(
    sub_game_number: int, my_role: str, end_reason: str, tampered: bool,
    my_group_id: str, their_group_id: str, config: GameConfig,
) -> dict:
    """Builds one Section-11 row for a finished sub-game."""
    result = "tamper_forfeit" if tampered else end_reason
    their_role = opposite_role(my_role)
    points = _score_table(config)[result]
    score = {my_group_id: points[my_role], their_group_id: points[their_role]}
    winner = None if score[my_group_id] == score[their_group_id] else (
        my_group_id if score[my_group_id] > score[their_group_id] else their_group_id
    )
    roles = {my_group_id: my_role, their_group_id: their_role}
    return build_sub_game_row(sub_game_number, result, roles, score, winner)


def _timeout_row(
    sub_game_number: int, role: str, my_group_id: str, their_group_id: str,
    started_at: str, ended_at: str, their_identity: dict, config: GameConfig,
) -> tuple[dict, dict, dict]:
    """Spec Section 13's own required fallback: a negotiate or audit call
    that never gets a matching response costs *this one sub-game alone* —
    scored `timeout` (0/0), unverified — never the whole series. Found
    live (rule-auditor cross-check against a real opponent's own interop
    guide): every ceiling here previously raised `DeadlineExceededError`
    straight out of `play_series`'s own loop, uncaught, aborting all
    remaining sub-games on a single transient drop."""
    row = _row_for(sub_game_number, role, "timeout", False, my_group_id, their_group_id, config)
    report_entry = {
        "sub_game_number": sub_game_number, "role": role, "end_reason": "timeout",
        "peer_result_claim": None, "verify": {"log_verified": False, "tampered": False, "mismatched_steps": []},
    }
    meta_entry = {
        "their_github_commit": their_identity.get("github_commit"),
        "steps": 0, "started_at": started_at, "ended_at": ended_at,
        "audit": {"log_verified": False, "tampered": False, "result_agreed": False},
        "has_log": False,
    }
    return row, report_entry, meta_entry
