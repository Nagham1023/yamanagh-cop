"""quantize_q_table / argmax_agreement_rate: round-trip, and proof the
metric actually catches a real divergence, not just passes by construction."""

from __future__ import annotations

from cop.reasoning.rl_checkpoint_quant import dequantize_q_table
from training.quantize import argmax_agreement_rate, quantize_q_table


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
