"""QTable: sparse, mutable Q-value store — the training-side half."""

from __future__ import annotations

from training.q_table import QTable

_STATE = (1, 2, 0)


def test_unvisited_state_action_defaults_to_zero():
    table = QTable()
    assert table.value(_STATE, "N") == 0.0


def test_update_then_read_round_trips():
    table = QTable()
    table.update(_STATE, "N", 4.5)
    assert table.value(_STATE, "N") == 4.5
    assert table.value(_STATE, "S") == 0.0  # untouched action in the same state


def test_best_value_is_max_over_all_actions_at_that_state():
    table = QTable()
    table.update(_STATE, "N", 1.0)
    table.update(_STATE, "E", 3.0)
    table.update(_STATE, "S", 2.0)
    assert table.best_value(_STATE) == 3.0


def test_best_value_on_unvisited_state_is_zero():
    table = QTable()
    assert table.best_value(_STATE) == 0.0


def test_best_legal_action_ignores_illegal_actions_even_if_they_score_higher():
    table = QTable()
    table.update(_STATE, "N", 10.0)
    table.update(_STATE, "E", 1.0)
    assert table.best_legal_action(_STATE, ["E", "S"]) == "E"


def test_best_legal_action_on_a_completely_unvisited_state_falls_to_first_by_tie():
    table = QTable()
    # all zero -> max() picks the first candidate in iteration order on ties
    assert table.best_legal_action(_STATE, ["S", "N"]) == "S"


def test_as_dict_reflects_all_updates_and_is_a_plain_dict():
    table = QTable()
    table.update(_STATE, "N", 4.5)
    as_dict = table.as_dict()
    assert as_dict == {_STATE: {"N": 4.5}}
    assert isinstance(as_dict, dict)
