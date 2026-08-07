"""memory/scent.py: the Figure-4 radial emission kernel and the combined
decay+deposit `advance()` step (PRD 4 Revision 1)."""

from __future__ import annotations

import pytest

from cop.domain.board import Board, Position
from cop.memory.scent import ScentField

_KERNEL_VALUES = {
    (0, 0): 0.90,
    (1, 0): 0.62, (-1, 0): 0.62, (0, 1): 0.62, (0, -1): 0.62,
    (1, 1): 0.42, (1, -1): 0.42, (-1, 1): 0.42, (-1, -1): 0.42,
    (2, 0): 0.20, (-2, 0): 0.20, (0, 2): 0.20, (0, -2): 0.20,
    (2, 1): 0.14, (2, -1): 0.14, (-2, 1): 0.14, (-2, -1): 0.14,
    (1, 2): 0.14, (1, -2): 0.14, (-1, 2): 0.14, (-1, -2): 0.14,
    (2, 2): 0.04, (2, -2): 0.04, (-2, 2): 0.04, (-2, -2): 0.04,
}


def _field(config) -> ScentField:
    return ScentField.from_config(config)


def test_advance_deposits_the_figure_4_radial_kernel_exactly(config):
    field = _field(config)
    board = Board(size=7)
    center = Position(3, 3)

    field.advance(center, board)

    sample = field.sample(center, board)
    assert len(_KERNEL_VALUES) == 25
    for (d_col, d_row), value in _KERNEL_VALUES.items():
        pos = Position(center.col + d_col, center.row + d_row)
        assert sample[pos] == pytest.approx(value), f"offset {(d_col, d_row)}"


def test_advance_composes_decay_and_fresh_deposit_additively(config):
    field = _field(config)
    board = Board(size=7)
    field.advance(Position(1, 1), board)
    before = field.sample(Position(1, 1), board)[Position(2, 1)]  # orthogonal, 0.62

    field.advance(Position(2, 1), board)  # (2,1) is now this turn's centre too

    after = field.sample(Position(1, 1), board)[Position(2, 1)]
    expected = before * (1 - config.scent_decay_rate) + config.scent_source_strength
    assert after == pytest.approx(expected)


def test_repeated_advance_at_a_fixed_point_converges_and_never_goes_negative(config):
    field = _field(config)
    board = Board(size=7)
    center = Position(3, 3)

    for _ in range(500):
        field.advance(center, board)

    level = field.sample(center, board)[center]
    steady_state = config.scent_source_strength / config.scent_decay_rate
    assert level == pytest.approx(steady_state, rel=1e-3)
    assert level >= 0.0


def test_a_previously_deposited_cell_outside_this_turns_kernel_only_decays(config):
    field = _field(config)
    board = Board(size=7)
    field.advance(Position(0, 0), board)
    before = field.sample(Position(0, 0), board)[Position(0, 2)]  # 0.20, in the first kernel

    field.advance(Position(6, 6), board)  # far away — kernel can't reach (0, 2)

    after = field.sample(Position(0, 0), board)[Position(0, 2)]
    assert after == pytest.approx(before * (1 - config.scent_decay_rate))


def test_advance_near_a_board_edge_only_deposits_in_bounds_cells():
    board = Board(size=7)
    field = ScentField(source_strength=0.9, decay_rate=0.10, window_size=5)

    field.advance(Position(0, 0), board)

    sample = field.sample(Position(0, 0), board)
    assert all(board.in_bounds(pos) for pos in sample)
    assert Position(-1, -1) not in sample
    assert Position(-2, -2) not in sample
    # A 5x5 kernel around a corner, clipped, only ever reaches cols/rows 0-2.
    assert sample.keys() == {Position(c, r) for c in range(3) for r in range(3)}


def test_unvisited_cells_read_as_zero_not_missing(config):
    field = _field(config)
    board = Board(size=config.board_size)

    sample = field.sample(Position(3, 3), board)

    assert sample[Position(3, 3)] == 0.0


def test_window_size_other_than_5_is_rejected():
    with pytest.raises(ValueError, match="5x5"):
        ScentField(source_strength=0.9, decay_rate=0.10, window_size=3)


def test_full_field_matches_internal_state_after_several_advances(config):
    # todoFullFix.md §C1: full_field() is the new scent-map tool's data
    # source — must expose everything sample()'s window would (and more:
    # cells far from any one center), not a lossy subset.
    field = _field(config)
    board = Board(size=7)
    field.advance(Position(1, 1), board)
    field.advance(Position(5, 5), board)  # far from the first deposit

    full = field.full_field()

    # Every cell the near-(1,1) kernel touched...
    for (d_col, d_row) in _KERNEL_VALUES:
        pos = Position(1 + d_col, 1 + d_row)
        if board.in_bounds(pos):
            assert full[pos] == field.sample(pos, board)[pos]
    # ...and the far deposit, both present in the same full-field snapshot —
    # sample() windowed around (1,1) would never show (5,5) at all.
    assert full[Position(5, 5)] == pytest.approx(0.90)


def test_full_field_never_holds_a_cell_never_advanced_near(config):
    field = _field(config)
    board = Board(size=7)
    field.advance(Position(0, 0), board)

    full = field.full_field()

    assert Position(6, 6) not in full  # far corner, never touched


def test_full_field_is_a_defensive_copy_not_the_live_internal_dict(config):
    field = _field(config)
    board = Board(size=7)
    field.advance(Position(3, 3), board)

    full = field.full_field()
    full[Position(3, 3)] = 999.0  # mutate the returned copy

    assert field.sample(Position(3, 3), board)[Position(3, 3)] != 999.0


def test_full_field_is_empty_before_any_advance(config):
    field = _field(config)
    assert field.full_field() == {}
