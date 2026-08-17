"""`play_series`: the top-level std_v1 entry point (spec Section 10's full
match lifecycle) — loops `series_sub_game.play_one_sub_game` across every
`num_games` sub-game (Section 6/10 [MATCH] role alternation: odd sub-games
play this repo's natural Police role, even sub-games flip to Thief), then
runs the final series-consensus exchange. Per-sub-game negotiate/play/audit
logic, and what a `DeadlineExceededError` there means (Section 13: that one
sub-game alone becomes `timeout`, never the whole series), lives in
`series_sub_game.py` — split out once this file crossed the 150-line cap.
"""

from __future__ import annotations

from ..planner.deadline import DeadlineExceededError
from ..shared.config import GameConfig
from .audit import (
    build_consensus_envelope,
    build_consensus_object,
    confirm_agreement,
    send_and_await,
    validate_consensus_envelope,
)
from .crypto import consensus_digest, derive_game_id, derive_game_uid
from .report import build_result_report, now_iso
from .roles import role_for_sub_game
from .series_sub_game import NATURAL_ROLE, play_one_sub_game


async def play_series(
    connection,
    exchange,
    my_terms: dict,
    my_group_id: str,
    their_group_id: str,
    identity: dict,
    turn_handler_factory,
    thief_components_factory,
    config: GameConfig,
    turn_deadline_sec: float = 10.0,
    resend_interval_sec: float = 2.0,
    negotiate_ceiling_sec: float = 300.0,
    audit_ceiling_sec: float = 60.0,
    sub_games_to_play: int | None = None,
    retry_attempts: int = 3,
    retry_delay_seconds: float = 1.0,
) -> dict:
    """Runs every sub-game (1..`my_terms["num_games"]`) to completion,
    then the final series-consensus exchange. `turn_handler_factory()` is
    only called on Police-role sub-games (builds a fresh `Std1TurnHandler`,
    position reset to the terms' own `cop_start`); `thief_components_
    factory()` is only called on alternated Thief-role sub-games (builds
    a fresh `(board, state, scent_field)`, position reset to the terms'
    own `thief_start`) — neither ever carries state over from the last
    sub-game.

    `sub_games_to_play`: spec Section 15's own compatibility-test launch
    parameter — "does not change the signed num_games", so this is
    deliberately a separate argument, never written into `my_terms`
    itself (that would change `game_uid`/the terms signature). `None`
    (the default) plays the full signed series unchanged; both peers
    MUST launch with the same count, or the shorter side finishes while
    the longer one waits on a sub-game that never arrives. `config`
    supplies the real scoring table and tie bonus (I6); `retry_attempts`/
    `retry_delay_seconds` are the shared connect-only retry budget for
    every wire call, sourced from `PrivateConfig` at the real call site."""
    game_id = derive_game_id(my_group_id, their_group_id)
    game_uid = derive_game_uid(my_terms, my_group_id, their_group_id)
    num_games = sub_games_to_play if sub_games_to_play is not None else my_terms["num_games"]

    rows: list[dict] = []
    sub_game_reports: list[dict] = []
    sub_game_meta: list[dict] = []
    their_identity: dict = {}
    all_clean = True
    game_started_at = now_iso()

    for sub_game_number in range(1, num_games + 1):
        exchange.reset_turns()
        role = role_for_sub_game(NATURAL_ROLE, sub_game_number)
        row, report_entry, meta_entry, log_verified, their_identity = await play_one_sub_game(
            connection, exchange, my_terms, my_group_id, their_group_id, identity,
            turn_handler_factory, thief_components_factory,
            sub_game_number, role, their_identity, config,
            turn_deadline_sec, resend_interval_sec, negotiate_ceiling_sec, audit_ceiling_sec,
            retry_attempts, retry_delay_seconds,
        )
        all_clean = all_clean and log_verified
        rows.append(row)
        sub_game_reports.append(report_entry)
        sub_game_meta.append(meta_entry)

    game_ended_at = now_iso()
    consensus_object = build_consensus_object(game_id, game_uid, rows)
    local_digest = consensus_digest(consensus_object)
    all_results_agreed = all(
        report["peer_result_claim"] == report["end_reason"] for report in sub_game_reports
    )

    final_role = role_for_sub_game(NATURAL_ROLE, num_games)
    try:
        peer_envelope = await send_and_await(
            connection,
            lambda timeout: exchange.wait_for_consensus(timeout),
            build_consensus_envelope(final_role, local_digest),
            resend_interval_sec, audit_ceiling_sec, retry_attempts, retry_delay_seconds,
        )
        peer_digest = validate_consensus_envelope(peer_envelope)
    except (DeadlineExceededError, ValueError):
        # Spec Section 13: a failure here means consensus may not confirm,
        # not that the whole series (already fully played) becomes invalid.
        peer_digest = ""
    agreed = confirm_agreement(all_clean, all_results_agreed, local_digest, peer_digest)
    mutual_agreement = {
        "sha256": local_digest,
        "peer_sha256": peer_digest,
        "sha_match": local_digest == peer_digest,
        "results_agreed": all_results_agreed,
        "confirmed": agreed,
    }
    report = build_result_report(
        game_id, game_uid, my_group_id, their_group_id, identity, their_identity,
        rows, sub_game_meta, mutual_agreement, game_started_at, game_ended_at,
        config.score_draw,
    )

    return {
        "game_id": game_id,
        "game_uid": game_uid,
        "consensus_object": consensus_object,
        "consensus_sha": local_digest,
        "peer_consensus_sha": peer_digest,
        "agreed": agreed,
        "sub_games": sub_game_reports,
        "report": report,
    }
