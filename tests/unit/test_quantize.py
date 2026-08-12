"""quantize_q_table / argmax_agreement_rate: round-trip, and proof the
metric actually catches a real divergence, not just passes by construction."""

from __future__ import annotations

from cop.reasoning.rl_checkpoint_quant import dequantize_q_table, dequantize_q_table_per_row
from training.quantize import argmax_agreement_rate, quantize_q_table, quantize_q_table_per_row


def test_quantize_then_dequantize_recovers_values_within_one_quantization_step():
    q_values = {(0, 0, 0): {"N": 12.5, "E": -3.2, "S": 0.0}}
    quantized, params = quantize_q_table(q_values)
    dequantized = dequantize_q_table(quantized, params)
    for action, original_value in q_values[(0, 0, 0)].items():
        assert abs(dequantized[(0, 0, 0)][action] - original_value) <= params.scale


def test_a_table_with_a_single_identical_value_dequantizes_exactly():
    q_values = {(0, 0, 0): {"N": 7.0, "E": 7.0}}
    quantized, params = quantize_q_table(q_values)
    dequantized = dequantize_q_table(quantized, params)
    assert dequantized[(0, 0, 0)] == {"N": 7.0, "E": 7.0}


def test_empty_table_quantizes_and_dequantizes_to_empty_without_dividing_by_zero():
    quantized, params = quantize_q_table({})
    assert quantized == {}
    assert dequantize_q_table(quantized, params) == {}


def test_argmax_agreement_is_perfect_on_a_well_separated_table():
    q_values = {(0, 0, 0): {"N": 100.0, "E": -100.0}, (1, 1, 0): {"E": -5.0, "N": 5.0}}
    quantized, params = quantize_q_table(q_values)
    assert argmax_agreement_rate(q_values, quantized, params) == 1.0


def test_argmax_agreement_catches_a_real_divergence_from_a_deliberate_near_tie():
    """A large table spread (dominated by one state's 100/-100 values)
    forces a coarse quantization step; a different state's genuine-but-tiny
    margin (0.0005) then collapses to a quantized tie, which resolves to
    the first-inserted key rather than the true original best — proving
    this metric actually detects the failure mode it exists to catch."""
    q_values = {
        (0, 0, 0): {"N": 100.0, "E": -100.0},
        (1, 1, 0): {"E": 0.0, "N": 0.0005},  # true best is N, by a hair
    }
    quantized, params = quantize_q_table(q_values)
    rate = argmax_agreement_rate(q_values, quantized, params)
    assert rate < 1.0
    assert rate == 0.5  # exactly one of the two states disagrees


def test_argmax_agreement_on_an_empty_table_is_one_not_a_crash():
    assert argmax_agreement_rate({}, {}, quantize_q_table({})[1]) == 1.0


def test_per_row_quantize_then_dequantize_recovers_values_within_that_rows_own_step():
    q_values = {(0, 0, 0): {"N": 12.5, "E": -3.2, "S": 0.0}, (1, 1, 0): {"STAY": 4.0}}
    quantized, params = quantize_q_table_per_row(q_values)
    dequantized = dequantize_q_table_per_row(quantized, params)
    for state, row in q_values.items():
        row_scale, _row_min_q = params.rows[state]
        for action, original_value in row.items():
            assert abs(dequantized[state][action] - original_value) <= row_scale


def test_per_row_rows_recover_independently_not_against_a_shared_table_scale():
    """A row's own recovery must depend only on *its own* values, not on
    what any other row in the same table happens to contain — the entire
    reason per-row mode exists. Two states share nothing in common except
    both being in the same table; each must still round-trip using its own
    (scale, min_q), not one bled in from the other."""
    q_values = {
        (0, 0, 0): {"N": 100.0, "E": -100.0},  # a huge spread
        (1, 1, 0): {"E": 0.0, "N": 0.0005},  # a tiny spread, in the same table
    }
    quantized, params = quantize_q_table_per_row(q_values)
    tiny_scale, _ = params.rows[(1, 1, 0)]
    huge_scale, _ = params.rows[(0, 0, 0)]
    assert tiny_scale < huge_scale  # each row's own resolution, not one shared value
    dequantized = dequantize_q_table_per_row(quantized, params)
    assert abs(dequantized[(1, 1, 0)]["N"] - 0.0005) <= tiny_scale


def test_per_row_resolves_the_cross_row_contamination_the_per_table_adversarial_case_exposed():
    """The exact q_values PRD 12's own per-table adversarial-divergence
    test uses: one state's huge spread (100/-100) forces per-table's single
    *shared* quantization step so coarse that a different state's genuine
    but tiny margin (0.0005) collapses into a tie (per-table's own rate:
    0.5). Per-row is structurally immune to this specific failure — each
    state gets its own step, so the huge-spread state can no longer degrade
    the tiny-spread state's resolution at all."""
    q_values = {
        (0, 0, 0): {"N": 100.0, "E": -100.0},
        (1, 1, 0): {"E": 0.0, "N": 0.0005},  # true best is N, by a hair
    }
    quantized, params = quantize_q_table_per_row(q_values)
    assert argmax_agreement_rate(q_values, quantized, params) == 1.0


def test_per_row_argmax_agreement_still_catches_a_real_within_row_divergence():
    """Per-row isn't immune to *every* precision loss — a single row that
    itself contains one dominant outlier value still forces a coarse local
    step for that same row's other, closely-spaced values, proving this
    metric genuinely measures something for per-row mode too, not a
    perpetual 1.0 by construction."""
    q_values = {(0, 0, 0): {"E": 0.0, "N": 0.0005, "W": -1000.0}}
    quantized, params = quantize_q_table_per_row(q_values)
    rate = argmax_agreement_rate(q_values, quantized, params)
    assert rate < 1.0
    assert rate == 0.0  # the table's only state disagrees
