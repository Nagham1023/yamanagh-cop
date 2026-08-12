"""QuantizationParams / dequantize_q_table: the production-side (decode-only) half."""

from __future__ import annotations

from cop.reasoning.rl_checkpoint_quant import (
    PerRowQuantizationParams,
    QuantizationParams,
    dequantize_any,
    dequantize_q_table,
    dequantize_q_table_per_row,
)


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


def test_dequantize_per_row_applies_each_states_own_affine_formula():
    params = PerRowQuantizationParams(
        dtype="int8", rows={(0, 0, 0): (2.0, -10.0), (1, 1, 0): (0.5, 3.0)}
    )
    quantized = {(0, 0, 0): {"N": -128, "E": 127}, (1, 1, 0): {"STAY": 0}}
    dequantized = dequantize_q_table_per_row(quantized, params)
    assert dequantized[(0, 0, 0)]["N"] == (-128 + 128) * 2.0 + -10.0
    assert dequantized[(0, 0, 0)]["E"] == (127 + 128) * 2.0 + -10.0
    assert dequantized[(1, 1, 0)]["STAY"] == (0 + 128) * 0.5 + 3.0


def test_dequantize_any_dispatches_on_the_params_type():
    per_table = QuantizationParams(dtype="int8", scale=1.0, min_q=0.0)
    per_row = PerRowQuantizationParams(dtype="int8", rows={(0, 0, 0): (1.0, 0.0)})
    quantized = {(0, 0, 0): {"N": 5}}
    assert dequantize_any(quantized, per_table) == dequantize_q_table(quantized, per_table)
    assert dequantize_any(quantized, per_row) == dequantize_q_table_per_row(quantized, per_row)
