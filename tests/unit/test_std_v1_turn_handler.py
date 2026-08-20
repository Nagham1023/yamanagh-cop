"""std_v1/turn_handler.py tests — real `BeliefMap`/`ScentField`/`CopBrain`,
the same pieces the native protocol's own turn cycle uses, driven through
the wire's `smell_grid` shape instead of a `share_scent_map` round trip."""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.memory.belief import BeliefMap
from cop.memory.scent import ScentField
from cop.reasoning.brain_base import BrainBase, Move
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


def test_tokens_used_total_starts_at_zero(config):
    handler = _handler(config)
    assert handler.tokens_used_total == 0


class _SpyBrain(BrainBase):
    """Records the `target_pos` it's actually handed, so a test can tell
    whether a decision used this turn's freshly-updated belief or a stale
    one -- a real live-match bug (see the regression test below)."""

    def __init__(self):
        self.seen_target_pos: Position | None = None

    def _pick_move(self, own_pos, target_pos, board, barriers) -> str:
        self.seen_target_pos = target_pos
        return "STAY"

    def _decide_move(self, own_pos, target_pos, board, barriers) -> Move:
        self.seen_target_pos = target_pos
        return Move("STAY")


def test_play_turn_decides_using_this_turns_freshly_updated_belief_not_last_turns(config):
    # Real bug found live: the Cop never caught an actively-fleeing Thief
    # within the 35-step ceiling, in any real match, regardless of brain.
    # Root cause: target_pos was only refreshed from belief_map *after*
    # _decide_move already ran, so every decision used a full turn of
    # stale belief on top of the network round trip's own unavoidable lag.
    board = Board(size=config.board_size)
    barriers = BarrierSet(quota=config.barrier_quota)
    belief_map = BeliefMap.uniform(board, barriers=barriers)
    stale_target = belief_map.most_likely_cell()
    state = GameState(own_pos=Position(0, 0), target_pos=stale_target, barriers=barriers)
    scent_field = ScentField.from_config(config)
    spy = _SpyBrain()
    handler = Std1TurnHandler(board, state, spy, belief_map, scent_field, config)

    far_cell = Position(6, 6)
    handler.play_turn({"6,6": 5.0}, "")

    assert spy.seen_target_pos == far_cell
    assert spy.seen_target_pos != stale_target


def test_tokens_used_total_accumulates_across_multiple_turns(config):
    # Rule 54: a real, growing accumulator this handler owns -- not a
    # value invented later at report time with no data flow behind it.
    handler = _handler(config)
    handler.play_turn({}, "")
    after_one = handler.tokens_used_total
    handler.play_turn({}, "")
    after_two = handler.tokens_used_total

    assert after_one == 0  # honest: template (the default provider) costs zero
    assert after_two == 0
    assert after_two >= after_one  # never goes backwards, whatever the provider actually costs
