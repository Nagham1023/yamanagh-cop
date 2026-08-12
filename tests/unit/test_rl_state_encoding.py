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


def test_default_belief_confidence_is_the_top_bucket():
    # Every pre-sub-layer-A caller (ground-truth training, run_local_subgame)
    # never passes belief_confidence at all — the default must land in the
    # same "maximally confident" bucket a real 1.0 reading would.
    barriers = BarrierSet(quota=14)
    default = encode_state(Position(0, 0), Position(3, 3), _BOARD, barriers)
    explicit_full_confidence = encode_state(
        Position(0, 0), Position(3, 3), _BOARD, barriers, belief_confidence=1.0
    )
    assert default == explicit_full_confidence


def test_near_uniform_confidence_lands_in_the_bottom_bucket():
    barriers = BarrierSet(quota=14)
    near_uniform = 1.0 / 49  # a 7x7 board's own uniform-prior peak probability
    state = encode_state(
        Position(0, 0), Position(3, 3), _BOARD, barriers, belief_confidence=near_uniform
    )
    top_confidence = encode_state(
        Position(0, 0), Position(3, 3), _BOARD, barriers, belief_confidence=1.0
    )
    assert state[3] == 0
    assert state[3] != top_confidence[3]


def test_confidence_bucket_is_monotonic_in_confidence():
    barriers = BarrierSet(quota=14)
    buckets = [
        encode_state(Position(0, 0), Position(3, 3), _BOARD, barriers, belief_confidence=c)[3]
        for c in (0.01, 0.1, 0.2, 0.4, 0.7, 1.0)
    ]
    assert buckets == sorted(buckets)  # a higher confidence never produces a lower bucket


def test_barrier_count_bucket_is_quota_relative_not_a_fixed_literal():
    board = _BOARD
    own_pos, target_pos = Position(0, 0), Position(3, 3)
    quota = 14  # thresholds at ~4.7 and ~9.3

    def state_at(count):
        placed = {Position(c, 6) for c in range(min(count, 6))}
        # pad past column 6 isn't possible on a 7-wide board — use two rows
        # instead so we can actually reach 10 distinct placed cells.
        if count > 6:
            placed |= {Position(c, 5) for c in range(count - 6)}
        return encode_state(own_pos, target_pos, board, BarrierSet(quota=quota, placed=placed))

    assert state_at(0)[4] == 0
    assert state_at(3)[4] == 1  # <= 14/3 ~= 4.67
    assert state_at(4)[4] == 1
    assert state_at(7)[4] == 2  # <= 2*14/3 ~= 9.33
    assert state_at(9)[4] == 2
    assert state_at(10)[4] == 3  # > 9.33


def test_enclosure_bucket_reflects_how_boxed_in_the_target_cell_is():
    board = _BOARD
    own_pos = Position(0, 0)

    cornered_target = Position(3, 3)
    cornered_barriers = BarrierSet(
        quota=14, placed={Position(2, 3), Position(4, 3), Position(3, 2), Position(3, 4)}
    )
    open_target = Position(3, 3)
    open_barriers = BarrierSet(quota=14)

    cornered_state = encode_state(own_pos, cornered_target, board, cornered_barriers)
    open_state = encode_state(own_pos, open_target, board, open_barriers)

    assert cornered_state[5] == 0  # fully walled in -> most cornered bucket
    assert open_state[5] == 2  # all four neighbours open -> least cornered bucket


def test_belief_based_state_can_genuinely_disagree_with_ground_truth():
    # The whole point of sub-layer A: encode_state() driven by a belief
    # estimate away from the true thief position must produce a *different*
    # state than the ground-truth position would.
    own_pos = Position(0, 0)
    true_thief_pos = Position(6, 6)
    believed_pos = Position(1, 1)  # far from the true position
    barriers = BarrierSet(quota=14)

    ground_truth_state = encode_state(own_pos, true_thief_pos, _BOARD, barriers)
    belief_state = encode_state(own_pos, believed_pos, _BOARD, barriers, belief_confidence=0.2)

    assert ground_truth_state != belief_state
