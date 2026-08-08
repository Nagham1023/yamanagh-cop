"""Rules 31/37/38/52: game-count bookkeeping, file-backed so it survives a
restart between sub-games in a real series.
"""

from __future__ import annotations

import pytest

from cop.policy.league_ledger import LeagueLedger


def test_recording_a_counted_game_against_a_new_opponent_increments_the_count(tmp_path):
    ledger = LeagueLedger(path=tmp_path / "ledger.json")

    ledger.record_counted_game("team-b")

    assert ledger.is_already_counted("team-b") is True
    assert ledger.counted_game_count() == 1


def test_recording_a_second_counted_game_against_an_already_counted_opponent_is_refused(tmp_path):
    ledger = LeagueLedger(path=tmp_path / "ledger.json")
    ledger.record_counted_game("team-b")

    with pytest.raises(ValueError, match="already has a counted game"):
        ledger.record_counted_game("team-b")

    assert ledger.counted_game_count() == 1  # the rejected attempt didn't double-count


def test_declare_at_game_start_reflects_the_true_count_across_multiple_games(tmp_path):
    ledger = LeagueLedger(path=tmp_path / "ledger.json")
    assert ledger.declare_at_game_start() == 0

    ledger.record_counted_game("team-b")
    assert ledger.declare_at_game_start() == 1

    ledger.record_counted_game("team-c")
    assert ledger.declare_at_game_start() == 2


def test_the_count_survives_a_restart_reading_the_same_file(tmp_path):
    path = tmp_path / "ledger.json"
    first_process = LeagueLedger(path=path)
    first_process.record_counted_game("team-b")

    second_process = LeagueLedger(path=path)  # simulates a new process, same file
    assert second_process.is_already_counted("team-b") is True
    assert second_process.counted_game_count() == 1


def test_a_fresh_ledger_with_no_file_yet_starts_empty(tmp_path):
    ledger = LeagueLedger(path=tmp_path / "does_not_exist_yet.json")
    assert ledger.counted_game_count() == 0
    assert ledger.is_already_counted("anyone") is False
