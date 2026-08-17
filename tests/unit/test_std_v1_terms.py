"""std_v1/terms.py tests — the 14-key closed set (Appendix A)."""

from __future__ import annotations

import pytest

from cop.std_v1.terms import DEFAULT_TERMS_PATH, TERM_KEYS, load_terms, validate_terms


def test_load_terms_reads_the_real_checked_in_file():
    terms = load_terms(DEFAULT_TERMS_PATH)
    assert set(terms) == set(TERM_KEYS)
    assert terms["board_size"] == 7
    assert terms["num_games"] == 6
    assert terms["thief_start"] == [3, 3]


def test_validate_terms_rejects_a_non_dict():
    with pytest.raises(ValueError, match="JSON object"):
        validate_terms(["not", "a", "dict"])


def test_validate_terms_rejects_a_missing_key():
    terms = load_terms(DEFAULT_TERMS_PATH)
    del terms["num_games"]
    with pytest.raises(ValueError, match="missing"):
        validate_terms(terms)


def test_validate_terms_rejects_an_extra_key():
    terms = load_terms(DEFAULT_TERMS_PATH)
    terms["extra_field"] = 1
    with pytest.raises(ValueError, match="unexpected"):
        validate_terms(terms)


def test_validate_terms_accepts_the_real_file():
    validate_terms(load_terms(DEFAULT_TERMS_PATH))  # must not raise


def test_term_keys_has_exactly_fourteen_entries():
    assert len(TERM_KEYS) == 14
