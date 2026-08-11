"""Quantization parameters and the dequantize direction (PRD 12).

Split out of `rl_checkpoint.py` to stay under the 150-line house cap once
quantization support landed — the constants/format half of that split
(CLAUDE.md's "extract constants/models into their own file" strategy).

Only *dequantize* lives here, in the production module: real inference
(`RLCopBrain`, via `load_checkpoint`) only ever needs to go from a quantized
checkpoint back to usable floats. The *quantize* (encode) direction is
training/promotion-only and lives in `training/quantize.py`, which imports
`QuantizationParams`/`dequantize_q_table` from here rather than
re-deriving the same affine formula — the same "one authoritative copy,
imported one-way" discipline `rl_state_encoding.py`/`rl_checkpoint.py`
already established for the encoding format itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rl_state_encoding import State


@dataclass(frozen=True)
class QuantizationParams:
    """Per-table affine int8 quantization: `stored = round((q - min_q) /
    scale) - 128`, `q ~= (stored + 128) * scale + min_q`. `scale` defaults
    to `1.0` when every value in the table is identical (a zero spread
    would otherwise divide by zero); dequantizing then correctly always
    recovers `min_q` exactly, see `training/quantize.py`."""

    dtype: str
    scale: float
    min_q: float


def dequantize_q_table(
    quantized: dict[State, dict[str, int]], params: QuantizationParams
) -> dict[State, dict[str, float]]:
    """Inverse of `training/quantize.py::quantize_q_table`'s encode step —
    the one place this formula is written; every caller imports it rather
    than re-deriving it (see module docstring)."""
    return {
        state: {action: (value + 128) * params.scale + params.min_q for action, value in row.items()}
        for state, row in quantized.items()
    }
