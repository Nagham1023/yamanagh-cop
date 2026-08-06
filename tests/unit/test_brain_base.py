"""BrainBase contract: the default _decide_move wraps _pick_move; the ABC can't be
instantiated directly."""

from __future__ import annotations

import pytest

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.reasoning.brain_base import BrainBase, Move


class _StubBrain(BrainBase):
    """Minimal concrete subclass — implements only what BrainBase requires."""

    def _pick_move(self, own_pos, target_pos, board, barriers) -> str:
        return "N"


def test_default_decide_move_wraps_pick_move_in_a_move_action():
    brain = _StubBrain()
    board = Board(size=7)
    barriers = BarrierSet(quota=14)

    action = brain._decide_move(Position(0, 0), Position(0, 5), board, barriers)

    assert action == Move(direction="N")


def test_brain_base_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BrainBase()
