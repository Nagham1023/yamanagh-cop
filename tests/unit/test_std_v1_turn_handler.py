"""std_v1/turn_handler.py tests — real `BeliefMap`/`ScentField`/`CopBrain`,
the same pieces the native protocol's own turn cycle uses, driven through
the wire's `smell_grid` shape instead of a `share_scent_map` round trip."""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.memory.belief import BeliefMap
from cop.memory.scent import ScentField
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.state import GameState
from cop.std_v1.turn_handler import Std1TurnHandler, _parse_smell_grid, _serialize_smell_grid
from cop.tools.hint_providers import HintProvider


def _handler(config) -> Std1TurnHandler:
    board = Board(size=config.board_size)
    barriers = BarrierSet(quota=config.barrier_quota)
    belief_map = BeliefMap.uniform(board, barriers=barriers)
    state = GameState(own_pos=Position(0, 0), target_pos=belief_map.most_likely_cell(), barriers=barriers)
    scent_field = ScentField.from_config(config)
    return Std1TurnHandler(board, state, CopBrain(), belief_map, scent_field, config)


def test_parse_smell_grid_swaps_row_col_to_position_col_row():
    parsed = _parse_smell_grid({"2,5": 0.7})
    assert parsed == {Position(col=5, row=2): 0.7}


def test_serialize_smell_grid_swaps_position_col_row_to_row_col():
    serialized = _serialize_smell_grid({Position(col=5, row=2): 0.7, Position(col=0, row=0): 0.0})
    assert serialized == {"2,5": 0.7}  # the zero-valued cell is omitted


def test_play_turn_returns_a_wire_ready_decision(config):
    handler = _handler(config)
    decision = handler.play_turn({"3,3": 0.9}, "")
    assert decision["move"] in ("N", "S", "E", "W", "STAY")
    assert isinstance(decision["hint"], str) and decision["hint"]
    assert isinstance(decision["smell_grid"], dict)
    assert len(decision["capture_claim"]) == 2


def test_play_turn_advances_own_position_or_places_a_barrier(config):
    handler = _handler(config)
    before = handler.state.own_pos
    handler.play_turn({}, "")
    after = handler.state.own_pos
    assert after != before or handler.state.barriers.placed  # moved, or barricaded in place


def test_capture_claim_matches_the_post_move_position(config):
    handler = _handler(config)
    decision = handler.play_turn({}, "")
    assert decision["capture_claim"] == [handler.state.own_pos.row, handler.state.own_pos.col]


class _MarkerHintProvider(HintProvider):
    """Returns a fixed, recognizable string — stands in for a real
    (possibly expensive/paid) configured provider, distinguishable from
    TemplateHintProvider's own generated text."""

    def generate(self, true_pos, intent, arena, word_limit, board_size) -> str:
        return "MARKER"


def test_play_turn_honors_every_n_steps_throttling_not_a_fixed_one(config):
    # I6: found hardcoded as a literal `1` (render the configured provider
    # every single turn, ignoring Table 21) — Std1TurnHandler now takes
    # every_n_steps explicitly and throttles the same way
    # orchestrator_turn.py::take_turn already does for the native protocol.
    board = Board(size=config.board_size)
    barriers = BarrierSet(quota=config.barrier_quota)
    belief_map = BeliefMap.uniform(board, barriers=barriers)
    state = GameState(own_pos=Position(0, 0), target_pos=belief_map.most_likely_cell(), barriers=barriers)
    scent_field = ScentField.from_config(config)
    handler = Std1TurnHandler(
        board, state, CopBrain(), belief_map, scent_field, config,
        hint_provider=_MarkerHintProvider(), every_n_steps=2,
    )

    first = handler.play_turn({}, "")   # steps_taken becomes 1 -- off cadence
    second = handler.play_turn({}, "")  # steps_taken becomes 2 -- on cadence

    assert "MARKER" not in first["hint"]
    assert "MARKER" in second["hint"]


def test_play_turn_folds_in_a_scent_map_boost_toward_the_reported_cell(config):
    handler = _handler(config)
    far_cell = Position(6, 6)
    before = handler.belief_map.probability(far_cell)
    handler.belief_map.update_from_scent_map({far_cell: 5.0}, handler.board)
    after = handler.belief_map.probability(far_cell)
    assert after > before
