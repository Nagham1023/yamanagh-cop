"""One sub-game's own negotiate+play+audit sequence — split out of
`series_runner.py`, which crossed the 150-line house cap once Section 13's
own required per-sub-game timeout isolation (below) landed. `play_series`
calls `play_one_sub_game` once per sub-game in its own loop; nothing here
knows about the series as a whole.
"""

from __future__ import annotations

from ..planner.deadline import DeadlineExceededError
from ..shared.config import GameConfig
from .audit import build_audit_envelope, send_and_await, verify_peer_records
from .handshake import negotiate_sub_game
from .report import now_iso
from .round_loop import play_sub_game
from .sub_game_rows import _row_for, _timeout_row
from .thief_round_loop import play_sub_game as play_sub_game_as_thief

NATURAL_ROLE = "police"


async def play_one_sub_game(
    connection, exchange, my_terms: dict, my_group_id: str, their_group_id: str, identity: dict,
    turn_handler_factory, thief_components_factory,
    sub_game_number: int, role: str, their_identity: dict, config: GameConfig,
    turn_deadline_sec: float, resend_interval_sec: float, negotiate_ceiling_sec: float, audit_ceiling_sec: float,
    retry_attempts: int, retry_delay_seconds: float,
) -> tuple[dict, dict, dict, bool, dict, dict | None]:
    """Returns `(row, report_entry, meta_entry, log_verified, their_identity,
    sub_game_log)` — `their_identity` comes back out since a successful
    negotiate is the only place it updates. `sub_game_log` is the raw
    transcript (both sides' records + the commits actually witnessed live)
    rule 20's replay verifier needs; `None` on a `timeout`, which has no
    transcript to log. A `DeadlineExceededError` anywhere here (negotiate,
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
            end_reason, records, peer_commits, my_commits = await play_sub_game(
                turn_handler, connection, exchange, max_steps, turn_deadline_sec,
                retry_attempts, retry_delay_seconds,
            )
            tokens_used = turn_handler.tokens_used_total
        else:
            # Rule 54: honest zero -- thief_round_loop.py never calls
            # generate_hint at all, always sending a bare hint="" (spec's
            # own convention), so there is nothing this side spent here.
            board, state, scent_field = thief_components_factory()
            end_reason, records, peer_commits, my_commits = await play_sub_game_as_thief(
                board, state, scent_field, connection, exchange, max_steps, turn_deadline_sec,
                retry_attempts, retry_delay_seconds,
            )
            tokens_used = 0

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
            "has_log": True,
            "tokens": tokens_used,
        }
        sub_game_log = {
            "sub_game_number": sub_game_number,
            "my_records": records, "my_commits": my_commits,
            "peer_records": peer_envelope.get("records", []), "peer_commits": peer_commits,
        }
        return row, report_entry, meta_entry, verify_result["log_verified"], their_identity, sub_game_log
    except DeadlineExceededError:
        row, report_entry, meta_entry = _timeout_row(
            sub_game_number, role, my_group_id, their_group_id, started_at, now_iso(), their_identity, config
        )
        return row, report_entry, meta_entry, False, their_identity, None
