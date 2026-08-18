"""Construction helpers for `peer.py::run_std_v1_peer` — split out once
that file grew past the 150-line house cap. `build_std_v1_game_config`
and `build_turn_handler_factory` together build everything a fresh
sub-game needs. `reporting.py` (a later, second split) holds everything
that runs after a series finishes — `write_std_v1_result`,
`write_std_v1_sub_game_logs`, `send_std_v1_report`.
"""

from __future__ import annotations

import dataclasses

from ..domain.barriers import BarrierSet
from ..domain.board import Board, Position
from ..memory.belief import BeliefMap
from ..memory.scent import ScentField
from ..reasoning.state import GameState
from ..shared.config import GameConfig
from ..shared.private_config import PrivateConfig
from ..tools.hint_providers import build_provider
from .turn_handler import Std1TurnHandler


def build_std_v1_game_config(base_config: GameConfig, terms: dict) -> GameConfig:
    """Overrides only the interop-relevant fields on an already-loaded
    native `GameConfig` with the signed std_v1 terms — scores/rate-limits/
    watchdog stay whatever the native shared config already set, since
    the spec's own consensus scoring (`series_runner.py`) is authoritative
    for std_v1, not this object's `score_*` fields."""
    return dataclasses.replace(
        base_config,
        board_size=terms["board_size"],
        thief_start=tuple(terms["thief_start"]),
        cop_start=tuple(terms["cop_start"]),
        barrier_quota=terms["barriers_max"],
        step_ceiling=terms["max_steps"],
        survival_threshold=terms["max_steps"],
        arena=terms["setting"],
        hint_word_limit=terms["hint_max_words"],
        scent_source_strength=terms["emit_intensity"],
        scent_decay_rate=terms["decay_per_step"],
        scent_field_size=terms["smell_grid_size"],
    )


def build_turn_handler_factory(config: GameConfig, private_config: PrivateConfig, brain_cls: type):
    """Returns a zero-arg factory building one fresh `Std1TurnHandler` —
    called once per sub-game by `series_runner.play_series`, so position,
    belief, and scent all reset to the terms' own `cop_start` every time."""

    def factory() -> Std1TurnHandler:
        board = Board(size=config.board_size)
        barriers = BarrierSet(quota=config.barrier_quota)
        belief_map = BeliefMap.uniform(board, barriers=barriers)
        state = GameState(
            own_pos=Position(*config.cop_start), target_pos=belief_map.most_likely_cell(), barriers=barriers
        )
        scent_field = ScentField.from_config(config)
        hint_provider = build_provider(private_config.provider)
        return Std1TurnHandler(
            board, state, brain_cls(), belief_map, scent_field, config, hint_provider,
            every_n_steps=private_config.every_n_steps,
        )

    return factory


def build_thief_components_factory(config: GameConfig):
    """Returns a zero-arg factory building `(board, state, scent_field)`
    fresh for one alternated Thief-role sub-game (spec Section 6) --
    position starts at the terms' own `thief_start`, `target_pos` is the
    terms' own public `cop_start` (thief_round_loop.py's own believed-cop
    fallback before anything has been sensed), never carrying state over
    from the previous sub-game."""

    def factory() -> tuple[Board, GameState, ScentField]:
        board = Board(size=config.board_size)
        barriers = BarrierSet(quota=config.barrier_quota)
        state = GameState(
            own_pos=Position(*config.thief_start), target_pos=Position(*config.cop_start), barriers=barriers
        )
        scent_field = ScentField.from_config(config)
        return board, state, scent_field

    return factory
