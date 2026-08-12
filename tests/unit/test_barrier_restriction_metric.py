"""barrier_restriction_metric: does a trained table's own barrier choices
already restrict the believed target's escape routes? See the module's own
docstring for why this is measured before any new reward term is built."""

from __future__ import annotations

from cop.reasoning.rl_checkpoint import load_checkpoint
from training.pipeline.barrier_restriction_metric import (
    barrier_restricts_relative_target,
    measure_barrier_restriction_rate,
)

_REAL_CHECKPOINT = "training/runs/prd14_gate_candidate_round1/checkpoint.json"


def test_barrier_restricts_relative_target_true_for_a_neighbour_of_the_target():
    # target at relative (2,0); BARRIER_E candidate at (1,0) -> distance 1
    assert barrier_restricts_relative_target("E", 2, 0) is True


def test_barrier_restricts_relative_target_false_for_a_non_adjacent_direction():
    # same target; BARRIER_N candidate at (0,-1) -> distance 3
    assert barrier_restricts_relative_target("N", 2, 0) is False


def test_returns_false_at_manhattan_distance_zero_matching_cop_brains_own_choice():
    # BARRIER_E candidate lands exactly on the target's own relative cell
    assert barrier_restricts_relative_target("E", 1, 0) is False


def test_measure_barrier_restriction_rate_on_a_synthetic_table_computes_the_correct_fraction():
    q_values = {
        (2, 0, 0, 3, 0, 2): {"BARRIER_E": 10.0, "N": 1.0},  # restricting (distance 1)
        (2, 0, 0, 3, 1, 2): {"BARRIER_N": 10.0, "N": 1.0},  # non-restricting (distance 3)
        (0, 0, 0, 3, 0, 2): {"N": 5.0, "E": 1.0},  # top action isn't a barrier -> excluded
        (1, 1, 0, 3, 0, 2): {"STAY": 5.0},  # top action isn't a barrier -> excluded
    }
    result = measure_barrier_restriction_rate(q_values)
    assert result["barrier_top_states"] == 2
    assert result["restricting"] == 1
    assert result["fraction_restricting"] == 0.5


def test_measure_barrier_restriction_rate_returns_none_when_no_barrier_top_states_exist():
    q_values = {(0, 0, 0, 3, 0, 2): {"N": 5.0, "E": 1.0}}
    result = measure_barrier_restriction_rate(q_values)
    assert result["barrier_top_states"] == 0
    assert result["fraction_restricting"] is None


def test_measure_against_the_real_prd14_checkpoint_produces_a_sane_number():
    table = load_checkpoint(_REAL_CHECKPOINT)
    result = measure_barrier_restriction_rate(table.as_dict())
    assert result["barrier_top_states"] >= 0
    if result["fraction_restricting"] is not None:
        assert 0.0 <= result["fraction_restricting"] <= 1.0
    print(f"\nreal checkpoint measurement: {result}")
