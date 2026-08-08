"""Validators for `GameConfig.from_dict` — split out of `config.py`, which
grew past the 150-line house cap once PRD 7's `rate_limiter_gatekeeper`/
`token_budget_per_series` fields landed alongside PRD 1-4's own. Every
numeric field is range/type-checked, not just presence-checked (TODO1.md
#4) — `ValueError` means a value is present but nonsensical or unsupported.
"""

from __future__ import annotations

from typing import Any


def positive_int(data: dict[str, Any], key: str) -> int:
    value = data[key]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{key} must be a positive int, got {value!r}")
    return value


def non_negative_int(data: dict[str, Any], key: str) -> int:
    value = data[key]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{key} must be a non-negative int, got {value!r}")
    return value


def string(data: dict[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string, got {value!r}")
    return value


def positive_number(data: dict[str, Any], key: str) -> float:
    """Like `positive_int`, but accepts a float too — timeouts (Table 19) are
    seconds, and a sub-second value is a legitimate thing to negotiate for a
    faster test suite, unlike board_size/quota/score fields which are always
    whole counts."""
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{key} must be a positive number, got {value!r}")
    return float(value)
