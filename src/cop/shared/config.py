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
`network_and_league`/`rate_limiter_gatekeeper`, plus top-level
`schema_version`/`agreed_between`) — confirmed by reading Appendix B directly
(p.126-132), not the flat, invented shape earlier PRDs used. This dataclass's
own attribute names stay unchanged: Appendix B governs the negotiated *file*
schema, not either team's internal naming, and every other module reads
fields via `config.<attr>`, name-agnostic to the JSON's shape — `from_dict()`
is the one translation point. `PARAMETERS.md`'s mapping table cross-references
the two naming schemes. Validators live in `config_validators.py` (split out
once PRD 7's own new fields pushed this file past the 150-line cap).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config_validators import non_negative_int, positive_int, positive_number, string

_SUPPORTED_ORIGIN = "top-left"
_SUPPORTED_INDEX_BASE = 0


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
    token_budget_per_series: int
    rate_limit_requests_per_minute: float
    rate_limit_concurrent_requests: int
    rate_limit_retry_backoff_seconds: float
    rate_limit_max_retries: int
    rate_limit_queue_depth: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameConfig:
        """Pull PRD 1-7's fields out of the full, Appendix-B-shaped config dict.

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
        rate_limiter_gatekeeper = data["rate_limiter_gatekeeper"]

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
            board_size=positive_int(board_and_agents, "grid_size"),
            agent_count=positive_int(board_and_agents, "num_agents"),
            origin=origin,
            index_base=index_base,
            thief_start=tuple(board_and_agents["thief_start"]),
            cop_start=tuple(board_and_agents["cop_start"]),
            barrier_quota=non_negative_int(movement_and_barriers, "max_barriers"),
            step_ceiling=positive_int(movement_and_barriers, "max_moves"),
            survival_threshold=positive_int(movement_and_barriers, "survival_threshold"),
            score_capture_cop=non_negative_int(scoring, "capture_cop"),
            score_capture_thief=non_negative_int(scoring, "capture_thief"),
            score_survival_cop=non_negative_int(scoring, "survival_cop"),
            score_survival_thief=non_negative_int(scoring, "survival_thief"),
            score_draw=non_negative_int(scoring, "tie_score"),
            response_timeout_seconds=positive_number(network_and_league, "response_timeout_sec"),
            watchdog_threshold_seconds=positive_number(network_and_league, "watchdog_timeout_sec"),
            arena=string(world, "map_area"),
            hint_word_limit=positive_int(world, "hint_max_words"),
            scent_source_strength=positive_number(pheromones, "pheromone_center_intensity"),
            scent_decay_rate=positive_number(pheromones, "pheromone_decay"),
            scent_field_size=positive_int(pheromones, "pheromone_grid_size"),
            schema_version=string(data, "schema_version"),
            agreed_between=tuple(data["agreed_between"]),
            token_budget_per_series=positive_int(network_and_league, "token_budget_per_series"),
            rate_limit_requests_per_minute=positive_number(
                rate_limiter_gatekeeper, "requests_per_minute"
            ),
            rate_limit_concurrent_requests=positive_int(
                rate_limiter_gatekeeper, "concurrent_requests"
            ),
            rate_limit_retry_backoff_seconds=positive_number(
                rate_limiter_gatekeeper, "retry_backoff_sec"
            ),
            rate_limit_max_retries=positive_int(rate_limiter_gatekeeper, "max_retries"),
            rate_limit_queue_depth=positive_int(rate_limiter_gatekeeper, "queue_depth"),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> GameConfig:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw)
