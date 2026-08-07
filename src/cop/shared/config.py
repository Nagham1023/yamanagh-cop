"""Config loading — the single place quantitative values leave the JSON file.

Invariant I6: every quantitative rule in the game is data, not code. Nothing
outside this module may hard-code a board size, a barrier quota, or a score.

`origin`/`index_base` are NEGOTIABLE (Table 13), but `Position`/`Board` only
implement top-left/index-0 — negotiating anything else is rejected here
loudly rather than silently misinterpreted three modules downstream
(TODO1.md #3). Every numeric field is range/type-checked, not just
presence-checked (TODO1.md #4). `arena` may legitimately be `""` (Table 14's
"generic landmarks" carve-out), so it's type-checked only, not non-empty.

`todoFullFix.md` §A2: `from_dict()` reads Appendix B's actual nested schema
(`board_and_agents`/`world`/`movement_and_barriers`/`scoring`/`pheromones`/
`network_and_league`, plus top-level `schema_version`/`agreed_between`) —
confirmed by reading Appendix B directly (p.126-132), not the flat, invented
shape earlier PRDs used. This dataclass's own attribute names stay
unchanged: Appendix B governs the negotiated *file* schema, not either
team's internal naming, and every other module reads fields via
`config.<attr>`, name-agnostic to the JSON's shape — `from_dict()` is the
one translation point. `PARAMETERS.md`'s mapping table cross-references the
two naming schemes.
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
    schema_version: str
    agreed_between: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameConfig:
        """Pull PRD 1-4's fields out of the full, Appendix-B-shaped config dict.

        `KeyError` means the config is *incomplete* — a missing nested group
        (e.g. no `board_and_agents` at all) fails loudly rather than
        defaulting quietly. `ValueError` means a value is present but
        nonsensical or unsupported (TODO1.md #3, #4).
        """
        board_and_agents = data["board_and_agents"]
        world = data["world"]
        movement_and_barriers = data["movement_and_barriers"]
        scoring = data["scoring"]
        pheromones = data["pheromones"]
        network_and_league = data["network_and_league"]

        origin = board_and_agents["axis_origin_corner"]
        index_base = board_and_agents["axis_start_index"]
        if origin != _SUPPORTED_ORIGIN or index_base != _SUPPORTED_INDEX_BASE:
            raise ValueError(
                f"origin={origin!r}/index_base={index_base!r} is a legal Table 13 "
                f"negotiation, but Position/Board only implement "
                f"origin={_SUPPORTED_ORIGIN!r}/index_base={_SUPPORTED_INDEX_BASE!r} "
                f"today — see TODO1.md #3 before accepting anything else."
            )

        return cls(
            board_size=_positive_int(board_and_agents, "grid_size"),
            agent_count=_positive_int(board_and_agents, "num_agents"),
            origin=origin,
            index_base=index_base,
            thief_start=tuple(board_and_agents["thief_start"]),
            cop_start=tuple(board_and_agents["cop_start"]),
            barrier_quota=_non_negative_int(movement_and_barriers, "max_barriers"),
            step_ceiling=_positive_int(movement_and_barriers, "max_moves"),
            survival_threshold=_positive_int(movement_and_barriers, "survival_threshold"),
            score_capture_cop=_non_negative_int(scoring, "capture_cop"),
            score_capture_thief=_non_negative_int(scoring, "capture_thief"),
            score_survival_cop=_non_negative_int(scoring, "survival_cop"),
            score_survival_thief=_non_negative_int(scoring, "survival_thief"),
            score_draw=_non_negative_int(scoring, "tie_score"),
            response_timeout_seconds=_positive_number(network_and_league, "response_timeout_sec"),
            watchdog_threshold_seconds=_positive_number(network_and_league, "watchdog_timeout_sec"),
            arena=_string(world, "map_area"),
            hint_word_limit=_positive_int(world, "hint_max_words"),
            scent_source_strength=_positive_number(pheromones, "pheromone_center_intensity"),
            scent_decay_rate=_positive_number(pheromones, "pheromone_decay"),
            scent_field_size=_positive_int(pheromones, "pheromone_grid_size"),
            schema_version=_string(data, "schema_version"),
            agreed_between=tuple(data["agreed_between"]),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> GameConfig:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw)
