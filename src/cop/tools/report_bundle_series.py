"""PRD 16: the real series-scoped `result_<game_id>.json` accumulation —
split from `report_bundle_result.py` once `SubGameEntry` landed alongside
it and the file re-hit the 150-line cap.

Ch. 9.4's own illustrative result-JSON schema (`schema_version`, `game_uid`,
`groups`, a `sub_games` array, a nested `final_result` object) is what
`merge_into_series_result` actually builds — `report_bundle.py`'s old
`build_result()` was a flat, single-sub-game-scoped dict with none of
this, an unflagged simplification this PRD closes.
"""

from __future__ import annotations

import uuid

from .report_bundle_result import SubGameEntry, build_mutual_agreement, winner_and_tie

_REPORT_SCHEMA_VERSION = "1.0"  # Table 20 locks the filename, not this internal schema (I6 n/a)
_REPORT_TYPE = "final_game_result"
_TIMEZONE = "UTC"  # _match_started_at/_match_ended_at are already ISO-8601 UTC


def _build_final_result(
    sub_games: list[dict],
    this_group: str,
    opponent_group: str,
    *,
    games_played_including_this: int,
    first_meeting_between_groups: bool,
) -> dict:
    """Recomputed from scratch each call, over `is_counted` entries only —
    matching `league_ledger.py`'s own "warm-ups are never recorded" scope."""
    counted = [g for g in sub_games if g["is_counted"]]
    this_total = sum(g["score"].get(this_group, 0) for g in counted)
    opponent_total = sum(g["score"].get(opponent_group, 0) for g in counted)
    winner_group, series_tie = winner_and_tie(this_group, this_total, opponent_group, opponent_total)
    # Table 18 row 4's own condition, self-reported truthfully — real
    # enforcement is the lecturer's cross-reference (league_ledger.py).
    diversity_reward_applied = first_meeting_between_groups and winner_group == this_group
    return {
        "total_score": {this_group: this_total, opponent_group: opponent_total},
        "sub_games_won": sum(1 for g in counted if g["winner_group"] == this_group),
        "ties": sum(1 for g in counted if g["tie"]),
        "winner_group": winner_group,
        "series_tie": series_tie,
        "tokens_total_series": {this_group: sum(g["tokens"][this_group] for g in counted), opponent_group: None},
        "games_played_including_this": games_played_including_this,
        "first_meeting_between_groups": first_meeting_between_groups,
        "diversity_reward_applied": diversity_reward_applied,
    }


def merge_into_series_result(
    previous: dict | None,
    entry: SubGameEntry,
    *,
    game_id: str,
    num_sub_games: int,
    games_played_including_this: int,
    first_meeting_between_groups: bool,
    repo_urls: dict[str, str],
    declaration_file: str,
) -> dict:
    """The real accumulation this repo's own docstrings already promised
    but never built: `sub_games` grows across separate `Orchestrator`
    process lifetimes (one per sub-game, PRD 10), keyed by
    `sub_game_number` — a re-run of the same sub-game updates in place
    rather than duplicating (idempotent).

    `repo_urls` (rule 49 **[FATAL]**: "four links in both teams' JSON") is
    this series' own constant four-URL set — `{this_cop, this_thief,
    opponent_cop, opponent_thief}` — recomputed fresh every call rather
    than merged, since it never changes sub-game to sub-game. `links`
    cross-references the other Table 20 files: `declaration` (one per
    series); each sub-game's own `config`/`log` already live inside its
    own `sub_games` entry (`log_files`)."""
    game_uid = previous["game_uid"] if previous is not None else str(uuid.uuid4())
    sub_games = list(previous["sub_games"]) if previous is not None else []
    sub_games = [g for g in sub_games if g["sub_game_number"] != entry.sub_game_number]
    sub_games.append(entry.to_dict())
    sub_games.sort(key=lambda g: g["sub_game_number"])

    payload = {
        "schema_version": _REPORT_SCHEMA_VERSION,
        "report_type": _REPORT_TYPE,
        "game_id": game_id,
        "game_uid": game_uid,
        "timezone": _TIMEZONE,
        "links": {"declaration": declaration_file},
        "repo_urls": repo_urls,
        "groups": [entry.this_group, entry.opponent_group],
        "num_sub_games": num_sub_games,
        "sub_games": sub_games,
        "final_result": _build_final_result(
            sub_games,
            entry.this_group,
            entry.opponent_group,
            games_played_including_this=games_played_including_this,
            first_meeting_between_groups=first_meeting_between_groups,
        ),
    }
    payload["mutual_agreement"] = build_mutual_agreement(
        payload, self_audit_passed=entry.log_verified, peer_audit_passed=entry.peer_audit_passed
    )
    return payload
