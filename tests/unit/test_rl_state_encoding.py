"""encode_state: relative-displacement, clamped, board-size-agnostic key."""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.reasoning.rl_state_encoding import encode_state

_BOARD = Board(size=7)


def test_encodes_relative_displacement_not_absolute_position():
    barriers = BarrierSet(quota=14)
    a = encode_state(Position(0, 0), Position(3, 3), _BOARD, barriers)
    b = encode_state(Position(1, 1), Position(4, 4), _BOARD, barriers)
    assert a[:2] == b[:2] == (3, 3)


def test_displacement_beyond_clamp_radius_saturates():
    barriers = BarrierSet(quota=14)
    near = encode_state(Position(0, 0), Position(4, 0), _BOARD, barriers)
    far = encode_state(Position(0, 0), Position(6, 0), _BOARD, barriers)
    assert near[0] == far[0]  # both clamp to the same saturated value


def test_negative_displacement_is_preserved_in_sign():
    barriers = BarrierSet(quota=14)
    state = encode_state(Position(5, 5), Position(2, 2), _BOARD, barriers)
    assert state[0] < 0
    assert state[1] < 0


def test_off_board_neighbours_set_bitmask_bits():
    barriers = BarrierSet(quota=14)
    corner = encode_state(Position(0, 0), Position(3, 3), _BOARD, barriers)
    center = encode_state(Position(3, 3), Position(3, 3), _BOARD, barriers)
    assert corner[2] != 0  # N and W are off-board from (0,0)
    assert center[2] == 0  # all four neighbours in-bounds and unblocked


def test_a_real_barrier_sets_a_bitmask_bit_a_pure_edge_state_would_not_have():
    own_pos = Position(3, 3)
    empty = BarrierSet(quota=14)
    blocked = BarrierSet(quota=14, placed={Position(3, 2)})  # north of (3,3)

    state_empty = encode_state(own_pos, Position(5, 5), _BOARD, empty)
    state_blocked = encode_state(own_pos, Position(5, 5), _BOARD, blocked)

    assert state_empty != state_blocked
    assert state_empty[2] == 0
    assert state_blocked[2] != 0


def test_deterministic_for_the_same_inputs():
    barriers = BarrierSet(quota=14)
    first = encode_state(Position(2, 2), Position(5, 5), _BOARD, barriers)
    second = encode_state(Position(2, 2), Position(5, 5), _BOARD, barriers)
    assert first == second
