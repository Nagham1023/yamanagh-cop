"""Quantization parameters and the dequantize direction (PRD 12; per-row
mode added PRD 14).

Split out of `rl_checkpoint.py` to stay under the 150-line house cap once
quantization support landed — the constants/format half of that split
(CLAUDE.md's "extract constants/models into their own file" strategy).

Only *dequantize* lives here, in the production module: real inference
(`RLCopBrain`, via `load_checkpoint`) only ever needs to go from a quantized
checkpoint back to usable floats. The *quantize* (encode) direction is
training/promotion-only and lives in `training/quantize.py`, which imports
both params types and both `dequantize_q_table*` functions from here rather
than re-deriving the same affine formula — the same "one authoritative
copy, imported one-way" discipline `rl_state_encoding.py`/`rl_checkpoint.py`
already established for the encoding format itself. On-disk JSON
serialization for both modes lives in the sibling `rl_checkpoint_json.py`
(a 50/50 math/serialization split, once per-row mode pushed this file past
the 150-line house cap).

**Per-row mode**: PRD 12 shipped one `(scale, min_q)` pair shared by the
*whole table* — a state whose Q-values cluster far from the table's global
extremes gets coarser resolution than its own local spread would need,
which PRD 12's own "explicitly out of scope" section named as the real
fix once argmax-agreement was ever judged too low (it now has been, twice:
90.84%, 91.22%). Per-row computes one `(scale, min_q)` pair *per state*
instead, from that state's own values only — same affine formula, finer
grain. `QuantizationParams`/`dequantize_q_table` (per-table) stay exactly
as they were: this is a second, coexisting mode, not a replacement.
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


@dataclass(frozen=True)
class PerRowQuantizationParams:
    """Same affine scheme as `QuantizationParams`, one `(scale, min_q)`
    pair per state instead of one shared by the whole table."""

    dtype: str
    rows: dict[State, tuple[float, float]]  # state -> (scale, min_q)


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


def dequantize_q_table_per_row(
    quantized: dict[State, dict[str, int]], params: PerRowQuantizationParams
) -> dict[State, dict[str, float]]:
    """Inverse of `training/quantize.py::quantize_q_table_per_row`'s encode
    step — same formula as `dequantize_q_table`, applied with each state's
    own `(scale, min_q)` from `params.rows` rather than one shared pair."""
    result: dict[State, dict[str, float]] = {}
    for state, row in quantized.items():
        scale, min_q = params.rows[state]
        result[state] = {action: (value + 128) * scale + min_q for action, value in row.items()}
    return result


def dequantize_any(
    quantized: dict[State, dict[str, int]],
    params: QuantizationParams | PerRowQuantizationParams,
) -> dict[State, dict[str, float]]:
    """Dispatches on `params`' own type — the one place both `load_checkpoint`
    and `training/quantize.py::argmax_agreement_rate` decide which
    dequantize function a checkpoint's mode calls for, so that decision
    exists exactly once."""
    if isinstance(params, PerRowQuantizationParams):
        return dequantize_q_table_per_row(quantized, params)
    return dequantize_q_table(quantized, params)
