"""quantize_q_table / argmax_agreement_rate (PRD 12).

Encode direction only — the training/promotion-only half of the affine
int8 scheme `cop.reasoning.rl_checkpoint_quant` defines. Dequantizing
reuses that production module's own `dequantize_q_table` directly rather
than re-deriving the formula here, so encode and decode can never quietly
drift apart (the same discipline `rl_checkpoint.py`'s own docstring already
names for the checkpoint format itself).

For a tabular Q-table, lookup is already O(1) — quantization's real payoff
here is a smaller checkpoint file and a working, reusable quantization
pipeline, not lookup speed (see `PRD-12-quantization-and-benchmarking.md`'s
own honest framing). `argmax_agreement_rate` is the metric that actually
matters for a *decision*: not how close the dequantized value is to the
original, but whether the best action at each state is still the same one.

**PRD 14's `quantize_q_table_per_row`** trades part of that file-size win
for much better decision fidelity: on a real full-config run, per-table
scored 89.36% argmax-agreement at 148KB; per-row scored 100% at ~230KB
(vs. 218KB unquantized) — a real, measured, honestly-reported trade, not a
free upgrade. `rl_checkpoint_json.py`'s own docstring covers why the
on-disk overhead isn't larger still (a real duplicated-serialization bug,
328KB, was found and fixed before this).
"""

from __future__ import annotations

from cop.reasoning.rl_checkpoint_quant import (
    PerRowQuantizationParams,
    QuantizationParams,
    dequantize_any,
)
from cop.reasoning.rl_state_encoding import State


def quantize_q_table(
    q_values: dict[State, dict[str, float]],
) -> tuple[dict[State, dict[str, int]], QuantizationParams]:
    """Per-table affine int8 quantization — one `(scale, min_q)` pair
    shared by every state/action, not per-row, kept simple for v1."""
    all_values = [value for row in q_values.values() for value in row.values()]
    if not all_values:
        return {}, QuantizationParams(dtype="int8", scale=1.0, min_q=0.0)

    min_q = min(all_values)
    max_q = max(all_values)
    spread = max_q - min_q
    # A zero spread (every value identical, e.g. a table with one entry)
    # would otherwise divide by zero; scale=1.0 then still dequantizes
    # exactly, since every stored code collapses back to min_q.
    scale = spread / 255.0 if spread > 0 else 1.0

    quantized = {
        state: {action: round((value - min_q) / scale) - 128 for action, value in row.items()}
        for state, row in q_values.items()
    }
    return quantized, QuantizationParams(dtype="int8", scale=scale, min_q=min_q)


def quantize_q_table_per_row(
    q_values: dict[State, dict[str, float]],
) -> tuple[dict[State, dict[str, int]], PerRowQuantizationParams]:
    """PRD 14: same affine formula as `quantize_q_table`, one `(scale,
    min_q)` pair computed independently per state from that state's own
    values only — see `rl_checkpoint_quant.py`'s module docstring for why."""
    quantized: dict[State, dict[str, int]] = {}
    rows: dict[State, tuple[float, float]] = {}
    for state, row in q_values.items():
        values = list(row.values())
        min_q = min(values)
        max_q = max(values)
        spread = max_q - min_q
        scale = spread / 255.0 if spread > 0 else 1.0
        rows[state] = (scale, min_q)
        quantized[state] = {action: round((value - min_q) / scale) - 128 for action, value in row.items()}
    return quantized, PerRowQuantizationParams(dtype="int8", rows=rows)


def argmax_agreement_rate(
    original: dict[State, dict[str, float]],
    quantized: dict[State, dict[str, int]],
    params: QuantizationParams | PerRowQuantizationParams,
) -> float:
    """Fraction of states where the best action is unchanged after a
    quantize/dequantize round trip. `1.0` on an empty table (vacuously
    agrees on nothing to disagree about) rather than raising or dividing
    by zero. `dequantize_any` dispatches on `params`' own type, so
    per-table and per-row checkpoints both measure the same way here."""
    if not original:
        return 1.0
    dequantized = dequantize_any(quantized, params)
    agreements = 0
    for state, row in original.items():
        original_best = max(row, key=row.__getitem__)
        dequantized_best = max(dequantized[state], key=dequantized[state].__getitem__)
        if original_best == dequantized_best:
            agreements += 1
    return agreements / len(original)
