"""One sub-game's own negotiate+play+audit sequence — split out of
`series_runner.py`, which crossed the 150-line house cap once Section 13's
own required per-sub-game timeout isolation (below) landed. `play_series`
calls `play_one_sub_game` once per sub-game in its own loop; nothing here
knows about the series as a whole.
"""

from __future__ import annotations

from ..planner.deadline import DeadlineExceededError
from ..shared.config import GameConfig
from .audit import build_audit_envelope, build_sub_game_row, send_and_await, verify_peer_records
from .handshake import negotiate_sub_game
from .report import now_iso
from .roles import opposite_role
from .round_loop import play_sub_game
from .thief_round_loop import play_sub_game as play_sub_game_as_thief

NATURAL_ROLE = "police"


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
    }
    return row, report_entry, meta_entry


async def play_one_sub_game(
    connection, exchange, my_terms: dict, my_group_id: str, their_group_id: str, identity: dict,
    turn_handler_factory, thief_components_factory,
    sub_game_number: int, role: str, their_identity: dict, config: GameConfig,
    turn_deadline_sec: float, resend_interval_sec: float, negotiate_ceiling_sec: float, audit_ceiling_sec: float,
    retry_attempts: int, retry_delay_seconds: float,
) -> tuple[dict, dict, dict, bool, dict]:
    """Returns `(row, report_entry, meta_entry, log_verified, their_identity)`
    — `their_identity` comes back out since a successful negotiate is the
    only place it updates. A `DeadlineExceededError` anywhere here (negotiate,
    gameplay wait, or the per-sub-game audit) is caught here, not left to
    `play_series`'s own loop, so it costs only this sub-game. `config`
    supplies the real scoring point table (I6); `retry_attempts`/
    `retry_delay_seconds` bound every wire call's own connect-only retry,
    both sourced from real config at `peer.py`'s call site."""
    max_steps = my_terms["max_steps"]
    started_at = now_iso()
    try:
        their_offer = await negotiate_sub_game(
            connection, exchange, my_terms, my_group_id, their_group_id,
            role, sub_game_number, identity, resend_interval_sec, negotiate_ceiling_sec,
            retry_attempts, retry_delay_seconds,
        )
        their_identity = their_offer.get("identity", their_identity)

        if role == "police":
            turn_handler = turn_handler_factory()
            end_reason, records, peer_commits = await play_sub_game(
                turn_handler, connection, exchange, max_steps, turn_deadline_sec,
                retry_attempts, retry_delay_seconds,
            )
        else:
            board, state, scent_field = thief_components_factory()
            end_reason, records, peer_commits = await play_sub_game_as_thief(
                board, state, scent_field, connection, exchange, max_steps, turn_deadline_sec,
                retry_attempts, retry_delay_seconds,
            )

        my_envelope = build_audit_envelope(role, records, end_reason, sub_game_number)
        peer_envelope = await send_and_await(
            connection,
            lambda timeout, n=sub_game_number: exchange.wait_for_audit(n, timeout),
            my_envelope, resend_interval_sec, audit_ceiling_sec, retry_attempts, retry_delay_seconds,
        )
        verify_result = verify_peer_records(peer_envelope.get("records", []), peer_commits)

        row = _row_for(
            sub_game_number, role, end_reason, verify_result["tampered"], my_group_id, their_group_id, config
        )
        report_entry = {
            "sub_game_number": sub_game_number,
            "role": role,
            "end_reason": end_reason,
            "peer_result_claim": peer_envelope.get("result_claim"),
            "verify": verify_result,
        }
        meta_entry = {
            "their_github_commit": their_identity.get("github_commit"),
            "steps": max((r.get("step", 0) for r in records), default=0),
            "started_at": started_at,
            "ended_at": now_iso(),
            "audit": {
                "log_verified": verify_result["log_verified"],
                "tampered": verify_result["tampered"],
                "result_agreed": peer_envelope.get("result_claim") == end_reason,
            },
        }
        return row, report_entry, meta_entry, verify_result["log_verified"], their_identity
    except DeadlineExceededError:
        row, report_entry, meta_entry = _timeout_row(
            sub_game_number, role, my_group_id, their_group_id, started_at, now_iso(), their_identity, config
        )
        return row, report_entry, meta_entry, False, their_identity
