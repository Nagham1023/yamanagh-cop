"""memory/belief.py: BeliefMap stays a genuine probability distribution
through every update, and shifts mass in the right direction."""

from __future__ import annotations

from cop.domain.board import Board, Position
from cop.memory.belief import BeliefMap
from cop.memory.scent import ScentField


def test_freshly_constructed_belief_map_sums_to_one_and_is_uniform(config):
    board = Board(size=config.board_size)
    belief = BeliefMap.uniform(board)

    assert abs(belief.total_probability() - 1.0) < 1e-9
    probabilities = {belief.probability(Position(c, r)) for c in range(board.size) for r in range(board.size)}
    assert len(probabilities) == 1  # all cells equal


def test_update_from_scent_keeps_summing_to_one_and_down_weights_searched_cells(config):
    board = Board(size=config.board_size)
    belief = BeliefMap.uniform(board)
    scent = ScentField.from_config(config)
    cop_pos = Position(3, 3)
    before = belief.probability(cop_pos)

    scent.advance(cop_pos, board)
    belief.update_from_scent(scent, cop_pos, board)

    assert abs(belief.total_probability() - 1.0) < 1e-9
    assert belief.probability(cop_pos) < before


def test_update_from_hint_keeps_summing_to_one_and_up_weights_the_focal_region(config):
    board = Board(size=config.board_size)
    belief = BeliefMap.uniform(board)
    focal_point = Position(6, 6)
    before = belief.probability(focal_point)

    belief.update_from_hint(focal_point, board)

    assert abs(belief.total_probability() - 1.0) < 1e-9
    assert belief.probability(focal_point) > before


def test_update_from_hint_never_zeroes_out_a_cell_boundary_case():
    # A corner focal point has only 2 in-bounds orthogonal neighbours —
    # confirm the update doesn't crash or corrupt the distribution there.
    board = Board(size=7)
    belief = BeliefMap.uniform(board)

    belief.update_from_hint(Position(0, 0), board)

    assert abs(belief.total_probability() - 1.0) < 1e-9


def test_most_likely_cell_returns_the_actual_argmax():
    # Construct a distribution with a known, deliberate peak directly —
    # update_from_hint boosts the focal cell *and* its orthogonal
    # neighbours by the same factor (found via reproduction: two identical
    # update_from_hint(peak) calls create a 5-way tie between peak and its
    # neighbours, not an unambiguous peak), so it's the wrong tool for
    # testing most_likely_cell's own correctness in isolation.
    board = Board(size=7)
    belief = BeliefMap.uniform(board)
    peak = Position(5, 2)
    belief._probabilities[peak] = 100.0

    assert belief.most_likely_cell() == peak


def test_update_from_scent_report_keeps_summing_to_one_and_up_weights_the_focal_region(config):
    board = Board(size=config.board_size)
    belief = BeliefMap.uniform(board)
    focal_point = Position(1, 1)
    before = belief.probability(focal_point)

    belief.update_from_scent_report(focal_point, board)

    assert abs(belief.total_probability() - 1.0) < 1e-9
    assert belief.probability(focal_point) > before


def test_scent_report_corroboration_outweighs_a_disagreeing_hint(config):
    # The actual corroboration mechanic: a (possibly-lying) hint pointing
    # one way and an always-truthful scent report pointing another way,
    # applied to the same fresh BeliefMap — the scent report's region
    # should end up more probable, since _SCENT_REPORT_BOOST > _HINT_BOOST.
    board = Board(size=config.board_size)
    belief = BeliefMap.uniform(board)
    lie_focal = Position(1, 1)
    truth_focal = Position(5, 5)

    belief.update_from_hint(lie_focal, board)
    belief.update_from_scent_report(truth_focal, board)

    assert belief.probability(truth_focal) > belief.probability(lie_focal)
