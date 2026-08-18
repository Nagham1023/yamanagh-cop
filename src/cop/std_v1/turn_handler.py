"""One Cop turn's full decision cycle for std_v1 — a synchronous,
std_v1-scoped analogue of `orchestrator_turn.py::BrainTurnMixin.take_turn`,
stripped of that mixin's async/commit-reveal specifics (std_v1's own
`sealing.py`/`wire.py` already are this protocol's commit-reveal layer)
and driven by the Thief's own `smell_grid`/hint carried inline on its
turn message, rather than a separate `share_scent_map` tool round trip.
Reuses the same real `BeliefMap`/`ScentField`/`BrainBase`/hint machinery
the native protocol's own turn cycle already uses — a different wire
format around identical belief/scent/brain logic, not a second one.
"""

from __future__ import annotations

import random

from ..domain.board import Board, Position
from ..memory.belief import BeliefMap
from ..memory.scent import ScentField
from ..reasoning.brain_base import BrainBase, Move, PlaceBarrier
from ..reasoning.hint import choose_provider, decide_intent, generate_hint, interpret_hint
from ..reasoning.state import GameState
from ..shared.config import GameConfig
from ..tools.hint_providers import HintProvider, TemplateHintProvider
from .capture import build_barrier_declaration, build_capture_claim

_DEFAULT_LIE_PROBABILITY = 0.0


def _parse_smell_grid(wire_grid: dict) -> dict[Position, float]:
    """The wire's `smell_grid` keys are `"row,col"` strings (the paired
    Thief repo's own `Cell` convention) — the opposite axis order from
    this repo's `Position(col, row)`, so every key is explicitly swapped."""
    parsed: dict[Position, float] = {}
    for key, value in wire_grid.items():
        row_str, col_str = key.split(",")
        parsed[Position(int(col_str), int(row_str))] = float(value)
    return parsed


def _serialize_smell_grid(field: dict[Position, float]) -> dict[str, float]:
    """The inverse of `_parse_smell_grid` — this repo's own scent field,
    wire-ready. Zero-or-below cells are omitted, matching the paired
    Thief repo's own "absence means zero" convention."""
    return {f"{pos.row},{pos.col}": value for pos, value in field.items() if value > 0.0}


class Std1TurnHandler:
    def __init__(
        self,
        board: Board,
        state: GameState,
        brain: BrainBase,
        belief_map: BeliefMap,
        scent_field: ScentField,
        config: GameConfig,
        hint_provider: HintProvider | None = None,
        rng: random.Random | None = None,
        every_n_steps: int = 1,
    ) -> None:
        """`config` should already be std_v1-scoped (board size, arena,
        hint word limit, scent constants all overridden from the signed
        terms) — see `std_v1_peer.py::_build_std_v1_config`. `every_n_steps`
        (Table 21, `PrivateConfig.every_n_steps`) throttles the real hint
        provider the same way `orchestrator_turn.py::take_turn` already
        does for the native protocol — I6, not a fixed `1`."""
        self.board = board
        self.state = state
        self.brain = brain
        self.belief_map = belief_map
        self.scent_field = scent_field
        self.config = config
        self.hint_provider = hint_provider or TemplateHintProvider()
        self.template_provider = TemplateHintProvider()
        self._rng = rng or random.Random()
        self.every_n_steps = every_n_steps
        self.tokens_used_total = 0  # rule 54: real, accumulated -- see play_turn

    def play_turn(self, thief_smell_grid: dict, thief_hint_text: str) -> dict:
        """Folds in the Thief's own scent report and hint, decides this
        turn's action, advances this repo's own scent/belief, and returns
        the wire-ready `{"move", "hint", "barrier_placed",
        "capture_claim"}` for this turn."""
        scent_data = _parse_smell_grid(thief_smell_grid)
        self.belief_map.update_from_scent_map(scent_data, self.board)
        focal_point = interpret_hint(thief_hint_text, self.board) if thief_hint_text else None
        if focal_point is not None:
            self.belief_map.update_from_hint(focal_point, self.board)

        action = self.brain._decide_move(
            self.state.own_pos, self.state.target_pos, self.board, self.state.barriers
        )
        self.state.apply(action, self.board)
        self.belief_map.zero_out_barriers(self.state.barriers)
        self.scent_field.advance(self.state.own_pos, self.board)
        self.belief_map.update_from_scent(self.scent_field, self.state.own_pos, self.board)
        self.state.target_pos = self.belief_map.most_likely_cell()

        intent = decide_intent(_DEFAULT_LIE_PROBABILITY, self._rng)
        provider = choose_provider(
            self.state.steps_taken, self.hint_provider, self.template_provider, self.every_n_steps
        )
        hint_text = generate_hint(self.state.own_pos, provider, self.config, intent)
        # Honest, not a magic number: template/ollama (Table 21's only
        # implemented providers, tools/hint_providers.py) really do cost
        # zero API tokens -- same reasoning orchestrator_turn.py's own
        # `_generate_and_log_hint` already uses for the native protocol.
        self.tokens_used_total += 0

        move_token = action.direction if isinstance(action, Move) else "STAY"
        barrier_placed = (
            build_barrier_declaration(action.target) if isinstance(action, PlaceBarrier) else None
        )
        return {
            "move": move_token,
            "hint": hint_text,
            "barrier_placed": barrier_placed,
            "capture_claim": build_capture_claim(self.state.own_pos),
            "smell_grid": _serialize_smell_grid(self.scent_field.full_field()),
        }
