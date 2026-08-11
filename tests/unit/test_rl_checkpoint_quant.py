"""QuantizationParams / dequantize_q_table: the production-side (decode-only) half."""

from __future__ import annotations

from cop.reasoning.rl_checkpoint_quant import QuantizationParams, dequantize_q_table


def test_dequantize_applies_the_documented_affine_formula():
    params = QuantizationParams(dtype="int8", scale=2.0, min_q=-10.0)
    quantized = {(0, 0, 0): {"N": -128, "E": 127}}
    dequantized = dequantize_q_table(quantized, params)
    assert dequantized[(0, 0, 0)]["N"] == (-128 + 128) * 2.0 + -10.0
    assert dequantized[(0, 0, 0)]["E"] == (127 + 128) * 2.0 + -10.0


def test_dequantize_of_an_empty_table_is_empty():
    params = QuantizationParams(dtype="int8", scale=1.0, min_q=0.0)
    assert dequantize_q_table({}, params) == {}


def test_dequantize_preserves_every_state_and_action_key():
    params = QuantizationParams(dtype="int8", scale=1.0, min_q=0.0)
    quantized = {(1, 2, 3): {"N": 0, "STAY": 10}, (0, 0, 0): {"E": -5}}
    dequantized = dequantize_q_table(quantized, params)
    assert set(dequantized) == set(quantized)
    assert set(dequantized[(1, 2, 3)]) == {"N", "STAY"}
