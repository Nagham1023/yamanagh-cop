"""Config loading — the single place quantitative values leave the JSON file.

Invariant I6 (CLAUDE.md/PLAN.md): every quantitative rule in the game is data,
not code. Nothing outside this module may hard-code a board size, a barrier
quota, or a score. `GameConfig` only exposes the fields PRD 1's domain layer
actually reads; later PRDs extend it rather than having every module parse
the raw JSON itself.

Two review findings (TODO1.md #3, #4) live here as loud failures instead of
silent bad behaviour surfacing three modules downstream:
  - `origin`/`index_base` are NEGOTIABLE (Table 13), but `Position`/`Board`
    only ever implement top-left/index-0. A config negotiating anything else
    would otherwise be silently misinterpreted, so it's rejected here until
    coordinate transforms actually exist.
  - Every numeric field is range/type-checked, not just presence-checked, so
    a malformed config fails at load time.

PRD 2 extends this dataclass with `response_timeout_seconds`/
`watchdog_threshold_seconds` (Table 19) — same pattern as PRD 1: each layer
adds the fields it needs rather than every module parsing the raw JSON.

PRD 4 extends it again with `arena`/`hint_word_limit` (Table 14) and
`scent_source_strength`/`scent_decay_rate`/`scent_field_size` (Table 16).
`arena` may legitimately be `""` (Table 14 #1's own "generic landmarks"
carve-out), so it's type-checked only, not non-empty-checked — a stricter
validator here would reject a value the book explicitly allows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SUPPORTED_ORIGIN = "top-left"
_SUPPORTED_INDEX_BASE = 0


def _positive_int(data: dict[str, Any], key: str) -> int:
    value = data[key]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{key} must be a positive int, got {value!r}")
    return value


def _non_negative_int(data: dict[str, Any], key: str) -> int:
    value = data[key]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{key} must be a non-negative int, got {value!r}")
    return value


def _string(data: dict[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string, got {value!r}")
    return value


def _positive_number(data: dict[str, Any], key: str) -> float:
    """Like `_positive_int`, but accepts a float too — timeouts (Table 19) are
    seconds, and a sub-second value is a legitimate thing to negotiate for a
    faster test suite, unlike board_size/quota/score fields which are always
    whole counts."""
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{key} must be a positive number, got {value!r}")
    return float(value)


@dataclass(frozen=True)
class GameConfig:
    board_size: int
    agent_count: int
    origin: str
    index_base: int
    thief_start: tuple[int, int]
    cop_start: tuple[int, int]
    barrier_quota: int
    step_ceiling: int
    survival_threshold: int
    score_capture_cop: int
    score_capture_thief: int
    score_survival_cop: int
    score_survival_thief: int
    score_draw: int
    response_timeout_seconds: float
    watchdog_threshold_seconds: float
    arena: str
    hint_word_limit: int
    scent_source_strength: float
    scent_decay_rate: float
    scent_field_size: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameConfig:
        """Pull PRD 1's fields out of the full config dict.

        Two independent failure modes, deliberately not collapsed into one:
        `KeyError` means the config is *incomplete* (Appendix F rule 1 —
        every value must be defined); `ValueError` means a value is present
        but nonsensical or unsupported (TODO1.md #3, #4).
        """
        origin = data["origin"]
        index_base = data["index_base"]
        if origin != _SUPPORTED_ORIGIN or index_base != _SUPPORTED_INDEX_BASE:
            raise ValueError(
                f"origin={origin!r}/index_base={index_base!r} is a legal Table 13 "
                f"negotiation, but Position/Board only implement "
                f"origin={_SUPPORTED_ORIGIN!r}/index_base={_SUPPORTED_INDEX_BASE!r} "
                f"today — see TODO1.md #3 before accepting anything else."
            )

        return cls(
            board_size=_positive_int(data, "board_size"),
            agent_count=data["agent_count"],
            origin=origin,
            index_base=index_base,
            thief_start=tuple(data["thief_start"]),
            cop_start=tuple(data["cop_start"]),
            barrier_quota=_non_negative_int(data, "barrier_quota"),
            step_ceiling=_positive_int(data, "step_ceiling"),
            survival_threshold=_positive_int(data, "survival_threshold"),
            score_capture_cop=_non_negative_int(data, "score_capture_cop"),
            score_capture_thief=_non_negative_int(data, "score_capture_thief"),
            score_survival_cop=_non_negative_int(data, "score_survival_cop"),
            score_survival_thief=_non_negative_int(data, "score_survival_thief"),
            score_draw=_non_negative_int(data, "score_draw"),
            response_timeout_seconds=_positive_number(data, "response_timeout_seconds"),
            watchdog_threshold_seconds=_positive_number(data, "watchdog_threshold_seconds"),
            arena=_string(data, "arena"),
            hint_word_limit=_positive_int(data, "hint_word_limit"),
            scent_source_strength=_positive_number(data, "scent_source_strength"),
            scent_decay_rate=_positive_number(data, "scent_decay_rate"),
            scent_field_size=_positive_int(data, "scent_field_size"),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> GameConfig:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw)
