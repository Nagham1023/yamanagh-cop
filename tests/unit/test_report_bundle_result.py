"""PRD 16: `SubGameEntry`/`build_mutual_agreement` (report_bundle_result.py)
and `merge_into_series_result` (report_bundle_series.py) — the real,
series-scoped `result_<game_id>.json` schema this PRD closes the gap on.
"""

from __future__ import annotations

from cop.tools.report_bundle_result import SubGameEntry, build_mutual_agreement, winner_and_tie
from cop.tools.report_bundle_series import merge_into_series_result


def _entry(**overrides) -> SubGameEntry:
    defaults = {
        "sub_game_number": 1,
        "this_group": "team-a",
        "opponent_group": "team-b",
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": "2026-01-01T00:05:00+00:00",
        "result": "capture",
        "this_score": 20,
        "opponent_score": 5,
        "this_commit": "a" * 40,
        "opponent_commit": "b" * 40,
        "this_tokens": 0,
        "config_file": "config_game1_g01.json",
        "log_file": "log_game1_g01.json",
        "log_verified": True,
        "peer_audit_passed": True,
        "is_counted": True,
    }
    defaults.update(overrides)
    return SubGameEntry(**defaults)


_REPO_URLS = {
    "team-a_cop": "https://github.com/team-a/cop",
    "team-a_thief": "https://github.com/team-a/thief",
    "team-b_cop": "https://github.com/team-b/cop",
    "team-b_thief": "https://github.com/team-b/thief",
}


def _merge(previous, entry, **overrides):
    defaults = {
        "game_id": "game1",
        "num_sub_games": 6,
        "games_played_including_this": 1,
        "first_meeting_between_groups": True,
        "repo_urls": _REPO_URLS,
        "declaration_file": "declaration_game1.json",
        "tie_score": 2,  # Table 17's own fixed value
    }
    defaults.update(overrides)
    return merge_into_series_result(previous, entry, **defaults)


def test_winner_and_tie_picks_the_higher_score():
    assert winner_and_tie("a", 20, "b", 5) == ("a", False)
    assert winner_and_tie("a", 5, "b", 20) == ("b", False)


def test_winner_and_tie_is_a_real_tie_on_equal_scores():
    assert winner_and_tie("a", 0, "b", 0) == (None, True)


def test_sub_game_entry_to_dict_derives_winner_group_and_tie_from_scores():
    entry = _entry(this_score=20, opponent_score=5)
    data = entry.to_dict()
    assert data["winner_group"] == "team-a"
    assert data["tie"] is False
    assert data["roles"] == {"team-a": "cop", "team-b": "thief"}
    assert data["score"] == {"team-a": 20, "team-b": 5}
    assert data["github_commit"] == {"team-a": "a" * 40, "team-b": "b" * 40}
    assert data["tokens"] == {"team-a": 0, "team-b": None}


def test_sub_game_entry_technical_loss_is_a_real_tie():
    entry = _entry(result="technical_loss", this_score=0, opponent_score=0)
    data = entry.to_dict()
    assert data["tie"] is True
    assert data["winner_group"] is None


def test_sub_game_entry_audit_tampered_is_false_only_when_both_audits_pass():
    both_pass = _entry(log_verified=True, peer_audit_passed=True).to_dict()
    assert both_pass["audit"] == {"log_verified": True, "peer_audit_passed": True, "tampered": False}

    self_failed = _entry(log_verified=False, peer_audit_passed=True).to_dict()
    assert self_failed["audit"]["tampered"] is True

    peer_failed = _entry(log_verified=True, peer_audit_passed=False).to_dict()
    assert peer_failed["audit"]["tampered"] is True


def test_build_mutual_agreement_confirmed_requires_both_audits():
    payload = {"a": 1}
    assert build_mutual_agreement(payload, self_audit_passed=True, peer_audit_passed=True)["confirmed"] is True
    assert build_mutual_agreement(payload, self_audit_passed=False, peer_audit_passed=True)["confirmed"] is False
    assert build_mutual_agreement(payload, self_audit_passed=True, peer_audit_passed=False)["confirmed"] is False


def test_build_mutual_agreement_sha256_changes_when_the_payload_changes():
    agreement_a = build_mutual_agreement({"a": 1}, self_audit_passed=True, peer_audit_passed=True)
    agreement_b = build_mutual_agreement({"a": 2}, self_audit_passed=True, peer_audit_passed=True)
    assert agreement_a["sha256"] != agreement_b["sha256"]


def test_merge_into_series_result_on_a_fresh_series_generates_a_game_uid_and_one_entry():
    result = _merge(None, _entry(sub_game_number=1))
    assert result["game_uid"]
    assert result["schema_version"] == "1.0"
    assert result["report_type"] == "final_game_result"
    assert result["groups"] == ["team-a", "team-b"]
    assert len(result["sub_games"]) == 1
    assert result["repo_urls"] == _REPO_URLS
    assert result["links"] == {"declaration": "declaration_game1.json"}


def test_merge_into_series_result_second_call_accumulates_not_replaces():
    first = _merge(None, _entry(sub_game_number=1, this_score=20, opponent_score=5))
    second = _merge(
        first, _entry(sub_game_number=2, this_score=5, opponent_score=10), first_meeting_between_groups=False
    )
    assert second["game_uid"] == first["game_uid"]  # same series identity, not regenerated
    assert [g["sub_game_number"] for g in second["sub_games"]] == [1, 2]
    assert second["final_result"]["total_score"] == {"team-a": 25, "team-b": 15}


def test_merge_into_series_result_applies_the_tie_score_bonus_once_on_a_series_tie():
    # Table 17's own tie_score = 2: config.score_draw was loaded but never
    # actually applied anywhere in this file — a real series tie
    # under-reported both sides' final score by the negotiated bonus.
    first = _merge(None, _entry(sub_game_number=1, this_score=20, opponent_score=5))
    second = _merge(
        first, _entry(sub_game_number=2, this_score=5, opponent_score=20), first_meeting_between_groups=False
    )
    assert second["final_result"]["total_score"] == {"team-a": 27, "team-b": 27}
    assert second["final_result"]["series_tie"] is True
    assert second["final_result"]["winner_group"] is None


def test_merge_into_series_result_does_not_apply_the_tie_score_bonus_when_not_tied():
    result = _merge(None, _entry(sub_game_number=1, this_score=20, opponent_score=5))
    assert result["final_result"]["total_score"] == {"team-a": 20, "team-b": 5}
    assert result["final_result"]["series_tie"] is False


def test_merge_into_series_result_resubmitting_the_same_sub_game_updates_in_place():
    first = _merge(None, _entry(sub_game_number=1, this_score=20, opponent_score=5))
    corrected = _merge(
        first, _entry(sub_game_number=1, this_score=0, opponent_score=0, result="technical_loss")
    )
    assert len(corrected["sub_games"]) == 1  # not duplicated
    assert corrected["sub_games"][0]["result"] == "technical_loss"


def test_final_result_ignores_a_warm_up_sub_game():
    first = _merge(None, _entry(sub_game_number=1, this_score=20, opponent_score=5, is_counted=True))
    with_warm_up = _merge(
        first,
        _entry(sub_game_number=2, this_score=100, opponent_score=0, is_counted=False),
        first_meeting_between_groups=False,
    )
    assert len(with_warm_up["sub_games"]) == 2  # still visible in the raw list
    assert with_warm_up["final_result"]["total_score"] == {"team-a": 20, "team-b": 5}  # warm-up excluded


def test_final_result_series_tie_when_counted_totals_are_equal():
    first = _merge(None, _entry(sub_game_number=1, this_score=20, opponent_score=5, result="capture"))
    tied = _merge(
        first,
        _entry(sub_game_number=2, this_score=5, opponent_score=20, result="capture"),
        first_meeting_between_groups=False,
    )
    assert tied["final_result"]["series_tie"] is True
    assert tied["final_result"]["winner_group"] is None


def test_diversity_reward_applied_only_on_a_first_meeting_win():
    result = _merge(None, _entry(sub_game_number=1, this_score=20, opponent_score=5))
    assert result["final_result"]["diversity_reward_applied"] is True

    not_first_meeting = _merge(
        None,
        _entry(sub_game_number=1, this_score=20, opponent_score=5),
        games_played_including_this=2,
        first_meeting_between_groups=False,
    )
    assert not_first_meeting["final_result"]["diversity_reward_applied"] is False


def test_merge_into_series_result_mutual_agreement_confirmed_reflects_this_entrys_audits():
    result = _merge(None, _entry(log_verified=False, peer_audit_passed=True))
    assert result["mutual_agreement"]["confirmed"] is False
    assert "sha256" in result["mutual_agreement"]
