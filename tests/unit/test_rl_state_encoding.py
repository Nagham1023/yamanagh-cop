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


def test_default_belief_entropy_is_the_top_zero_entropy_bucket():
    # Every pre-sub-layer-A caller (ground-truth training, run_local_subgame)
    # never passes belief_entropy at all — the default must land in the
    # same "zero entropy, maximally certain" bucket a real point mass would.
    barriers = BarrierSet(quota=14)
    default = encode_state(Position(0, 0), Position(3, 3), _BOARD, barriers)
    explicit_zero_entropy = encode_state(
        Position(0, 0), Position(3, 3), _BOARD, barriers, belief_entropy=0.0
    )
    assert default == explicit_zero_entropy


def test_high_entropy_lands_in_the_bottom_high_ambiguity_bucket():
    barriers = BarrierSet(quota=14)
    high_entropy = 3.9  # above the ENTROPY_THRESHOLDS top boundary (2.5)
    state = encode_state(
        Position(0, 0), Position(3, 3), _BOARD, barriers, belief_entropy=high_entropy
    )
    zero_entropy = encode_state(
        Position(0, 0), Position(3, 3), _BOARD, barriers, belief_entropy=0.0
    )
    assert state[3] == 0
    assert state[3] != zero_entropy[3]


def test_entropy_bucket_is_monotonic_in_entropy_higher_entropy_never_a_higher_bucket():
    barriers = BarrierSet(quota=14)
    buckets = [
        encode_state(Position(0, 0), Position(3, 3), _BOARD, barriers, belief_entropy=h)[3]
        for h in (0.0, 0.5, 1.0, 1.5, 2.5, 3.9)
    ]
    assert buckets == sorted(buckets, reverse=True)  # higher entropy never a higher bucket


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
    belief_state = encode_state(own_pos, believed_pos, _BOARD, barriers, belief_entropy=1.8)

    assert ground_truth_state != belief_state


def test_no_second_mode_encodes_dx2_dy2_as_zero():
    barriers = BarrierSet(quota=14)
    state = encode_state(Position(0, 0), Position(3, 3), _BOARD, barriers)
    assert state[6:8] == (0, 0)
    explicit_none = encode_state(
        Position(0, 0), Position(3, 3), _BOARD, barriers, second_mode_pos=None
    )
    assert explicit_none == state


def test_a_real_second_mode_produces_correctly_clamped_relative_values():
    barriers = BarrierSet(quota=14)
    own_pos = Position(0, 0)
    state = encode_state(
        own_pos, Position(3, 3), _BOARD, barriers, second_mode_pos=Position(3, 1)
    )
    assert state[6:8] == (3, 1)


def test_second_mode_displacement_beyond_clamp_radius_saturates_same_as_the_primary():
    barriers = BarrierSet(quota=14)
    own_pos = Position(0, 0)
    near = encode_state(own_pos, Position(3, 3), _BOARD, barriers, second_mode_pos=Position(4, 0))
    far = encode_state(own_pos, Position(3, 3), _BOARD, barriers, second_mode_pos=Position(6, 0))
    assert near[6] == far[6]  # both saturate to the same clamped value


def test_state_shape_is_now_an_eight_tuple():
    # A real, checked shape assertion -- not just "it doesn't crash" -- since
    # a silent 6-vs-8 shape drift is exactly what the checkpoint version
    # guard (rl_checkpoint.py) exists to catch at load time; this confirms
    # the encoder side produces the shape that guard expects.
    barriers = BarrierSet(quota=14)
    state = encode_state(Position(0, 0), Position(3, 3), _BOARD, barriers)
    assert len(state) == 8
