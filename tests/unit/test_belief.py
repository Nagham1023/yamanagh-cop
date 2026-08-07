"""memory/belief.py: BeliefMap stays a genuine probability distribution
through every update, and shifts mass in the right direction."""

from __future__ import annotations

from cop.domain.barriers import BarrierSet
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


def test_update_from_scent_map_keeps_summing_to_one_and_up_weights_a_hot_cell(config):
    # PRD 4 "Revision 3" (todoFullFix.md §C8): update_from_scent_map takes
    # real per-cell data, not a single re-quantized focal Position.
    board = Board(size=config.board_size)
    belief = BeliefMap.uniform(board)
    hot_cell = Position(1, 1)
    before = belief.probability(hot_cell)

    belief.update_from_scent_map({hot_cell: 0.9}, board)

    assert abs(belief.total_probability() - 1.0) < 1e-9
    assert belief.probability(hot_cell) > before


def test_update_from_scent_map_scales_with_the_actual_magnitude():
    # A strong reading must end up more probable than a weak one at the
    # same cell — proves the update uses real tau values, not a flat
    # factor applied uniformly to any nonzero cell (a degraded quadrant
    # guess in disguise would fail this).
    board = Board(size=7)
    strong = BeliefMap.uniform(board)
    weak = BeliefMap.uniform(board)
    cell = Position(3, 3)

    strong.update_from_scent_map({cell: 0.9}, board)
    weak.update_from_scent_map({cell: 0.1}, board)

    assert strong.probability(cell) > weak.probability(cell)


def test_update_from_scent_map_leaves_absent_cells_relatively_worse_off():
    # A cell with no entry in scent_data gets no direct boost — its share
    # of the total must shrink as other cells' shares grow, not stay flat.
    board = Board(size=7)
    belief = BeliefMap.uniform(board)
    untouched = Position(6, 6)
    before = belief.probability(untouched)

    belief.update_from_scent_map({Position(0, 0): 0.9}, board)

    assert belief.probability(untouched) < before


def test_scent_map_corroboration_outweighs_a_disagreeing_hint(config):
    # The actual corroboration mechanic: a (possibly-lying) hint pointing
    # one way and the peer's own real scent data pointing another way,
    # applied to the same fresh BeliefMap — the scent map's region should
    # end up more probable, tuned so a real scent reading can overcome the
    # hint's own region-concentration head start (todoFullFix.md §E).
    board = Board(size=config.board_size)
    belief = BeliefMap.uniform(board)
    lie_focal = Position(1, 1)
    truth_cell = Position(5, 5)

    belief.update_from_hint(lie_focal, board)
    belief.update_from_scent_map({truth_cell: 0.9}, board)

    assert belief.probability(truth_cell) > belief.probability(lie_focal)


def test_update_from_scent_map_with_a_real_scent_field_favors_the_true_trail(config):
    # End-to-end with a genuine ScentField.full_field() output (not a
    # hand-built dict), matching how take_turn() actually calls this.
    board = Board(size=config.board_size)
    belief = BeliefMap.uniform(board)
    scent = ScentField.from_config(config)
    true_pos = Position(5, 5)
    scent.advance(true_pos, board)

    belief.update_from_scent_map(scent.full_field(), board)

    assert belief.most_likely_cell() == true_pos


def test_a_higher_reliability_coefficient_shifts_belief_more_than_a_lower_one(monkeypatch):
    # todoFullFix.md §E: proves _HINT_RELIABILITY is genuinely load-bearing
    # — a hint declared more reliable must concentrate belief harder on its
    # focal region than the identical hint declared less reliable, not just
    # produce the same shift regardless of the coefficient's value.
    import cop.memory.belief as belief_module

    board = Board(size=7)
    focal_point = Position(3, 3)

    monkeypatch.setattr(belief_module, "_HINT_RELIABILITY", 0.55)
    low = BeliefMap.uniform(board)
    low.update_from_hint(focal_point, board)

    monkeypatch.setattr(belief_module, "_HINT_RELIABILITY", 0.95)
    high = BeliefMap.uniform(board)
    high.update_from_hint(focal_point, board)

    assert high.probability(focal_point) > low.probability(focal_point)


def test_uniform_with_barriers_seeds_them_at_exactly_zero_from_construction():
    # todoFullFix.md §E1: not just "zeroed after a later update" — a
    # barrier already known at construction time must never have carried
    # nonzero belief in the first place.
    board = Board(size=7)
    barriers = BarrierSet(quota=5)
    barrier_cell = Position(3, 3)
    barriers.placed.add(barrier_cell)

    belief = BeliefMap.uniform(board, barriers=barriers)

    assert belief.probability(barrier_cell) == 0.0
    assert abs(belief.total_probability() - 1.0) < 1e-9
    non_barrier_probabilities = {
        belief.probability(Position(c, r))
        for c in range(board.size)
        for r in range(board.size)
        if Position(c, r) != barrier_cell
    }
    assert len(non_barrier_probabilities) == 1  # every other cell still equal
    assert next(iter(non_barrier_probabilities)) > 0.0


def test_zero_out_barriers_zeroes_an_existing_cells_belief_and_renormalizes():
    board = Board(size=7)
    belief = BeliefMap.uniform(board)
    barrier_cell = Position(4, 4)
    before = belief.probability(barrier_cell)
    assert before > 0.0

    barriers = BarrierSet(quota=5)
    barriers.placed.add(barrier_cell)
    belief.zero_out_barriers(barriers)

    assert belief.probability(barrier_cell) == 0.0
    assert abs(belief.total_probability() - 1.0) < 1e-9
    # the zeroed mass must have gone *somewhere*, not vanished
    other_cell = Position(0, 0)
    assert belief.probability(other_cell) > before


def test_a_barrier_cell_never_wins_most_likely_cell_even_though_it_would_under_unfiltered_argmax():
    # Constructed so the barrier cell would win a plain, unfiltered
    # max(probabilities) — proves most_likely_cell()'s own exclusion is
    # real, not just relying on the value happening to already be lowest.
    board = Board(size=7)
    belief = BeliefMap.uniform(board)
    barrier_cell = Position(2, 2)
    belief._probabilities[barrier_cell] = 999.0  # would trivially win an unfiltered argmax
    barriers = BarrierSet(quota=1)
    barriers.placed.add(barrier_cell)
    belief.zero_out_barriers(barriers)

    # zero_out_barriers already re-zeroed the artificially huge value, but
    # most_likely_cell()'s own filter is the second, independent layer —
    # sabotage-test it directly by restoring the huge raw value afterward
    # without going through zero_out_barriers again.
    belief._probabilities[barrier_cell] = 999.0

    assert belief.most_likely_cell() != barrier_cell


def test_most_likely_cell_falls_back_when_every_cell_is_somehow_a_barrier():
    # Genuinely unreachable in real play (barrier_quota is well under board
    # cell count per Appendix F), but most_likely_cell()'s own defensive
    # fallback exists specifically for this case — tested directly rather
    # than left as untested dead code.
    board = Board(size=2)
    barriers = BarrierSet(quota=4)
    all_cells = {Position(c, r) for c in range(2) for r in range(2)}
    barriers.placed |= all_cells
    belief = BeliefMap.uniform(board, barriers=barriers)

    assert belief.most_likely_cell() in all_cells
