"""std_v1/capture.py tests — wire coordinates are `[row, col]`, the
opposite axis order from this repo's own `Position(col, row)`."""

from __future__ import annotations

from cop.domain.board import Position
from cop.std_v1.capture import build_barrier_declaration, build_capture_claim, was_caught


def test_build_capture_claim_swaps_to_row_col_order():
    assert build_capture_claim(Position(col=4, row=2)) == [2, 4]


def test_build_barrier_declaration_swaps_to_row_col_order():
    assert build_barrier_declaration(Position(col=1, row=5)) == [5, 1]


def test_was_caught_true_when_claim_response_confirms():
    assert was_caught({"claim": [2, 4], "caught": True}) is True


def test_was_caught_false_when_claim_response_denies():
    assert was_caught({"claim": [2, 4], "caught": False}) is False


def test_was_caught_false_when_no_claim_response_yet():
    assert was_caught(None) is False


def test_was_caught_false_on_an_empty_dict():
    assert was_caught({}) is False
