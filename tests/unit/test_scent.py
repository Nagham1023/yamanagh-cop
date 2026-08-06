"""memory/scent.py: ScentField emission, decay, and windowed sampling."""

from __future__ import annotations

from cop.domain.board import Board, Position
from cop.memory.scent import ScentField


def _field(config) -> ScentField:
    return ScentField.from_config(config)


def test_emit_then_sample_shows_the_emitted_cell_at_source_strength(config):
    field = _field(config)
    board = Board(size=config.board_size)
    field.emit(Position(3, 3))

    sample = field.sample(Position(3, 3), board)

    assert sample[Position(3, 3)] == config.scent_source_strength


def test_one_decay_call_reduces_a_cell_by_exactly_the_configured_rate(config):
    field = _field(config)
    board = Board(size=config.board_size)
    field.emit(Position(3, 3))

    field.decay()

    expected = config.scent_source_strength * (1 - config.scent_decay_rate)
    assert field.sample(Position(3, 3), board)[Position(3, 3)] == expected


def test_repeated_decay_approaches_zero_and_never_goes_negative(config):
    field = _field(config)
    board = Board(size=config.board_size)
    field.emit(Position(3, 3))

    for _ in range(200):
        field.decay()

    level = field.sample(Position(3, 3), board)[Position(3, 3)]
    assert 0.0 <= level < 1e-6


def test_unvisited_cells_read_as_zero_not_missing(config):
    field = _field(config)
    board = Board(size=config.board_size)

    sample = field.sample(Position(3, 3), board)

    assert sample[Position(3, 3)] == 0.0


def test_sample_near_a_board_edge_returns_only_in_bounds_cells():
    config_board = Board(size=7)
    field = ScentField(source_strength=0.9, decay_rate=0.10, window_size=5)

    sample = field.sample(Position(0, 0), config_board)

    assert all(config_board.in_bounds(pos) for pos in sample)
    assert Position(-1, -1) not in sample
    assert Position(-2, -2) not in sample
    # A 5x5 window around a corner, clipped, is a 3x3 quadrant: cols/rows 0-2.
    assert sample.keys() == {Position(c, r) for c in range(3) for r in range(3)}
