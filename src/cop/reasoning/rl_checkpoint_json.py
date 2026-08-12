"""On-disk JSON shape of a checkpoint's `"quantization"` key and `"q_values"`
entries (PRD 14) — split out of `rl_checkpoint_quant.py` once per-row mode
pushed that file past the 150-line house cap (a 50/50 split: quantization
*math* stayed there, quantization *serialization* moved here).

Per-row `(scale, min_q)` is stored *inline in each q_values entry*, not in a
separate "rows" list keyed by state — a real, measured problem found while
building this mode: a separate list re-serializes every state's key a
second time, and Python's default float repr carries ~17 significant
digits nothing here needs (int8 quantization's own resolution is ~1/255
relative). Together those turned a "smaller checkpoint" feature into a
*larger-than-unquantized* one on a real ~2400-state table (328KB per-row
vs. 218KB unquantized, vs. 148KB per-table) before this fix. Rounding to 10
decimal places is far finer than the quantization step itself ever
resolves, so it costs no real accuracy — verified by `argmax_agreement_rate`
staying unchanged before vs. after rounding on a real table, not assumed.
"""

from __future__ import annotations

from typing import Any

from .rl_checkpoint_quant import PerRowQuantizationParams, QuantizationParams
from .rl_state_encoding import State

_ROW_PRECISION = 10  # decimal places for a serialized (scale, min_q) pair


def quantization_to_json(
    quantization: QuantizationParams | PerRowQuantizationParams | None,
) -> dict | None:
    """The on-disk shape of the checkpoint's `"quantization"` key — `None`
    (PRD 11's unquantized shape) unchanged; a `"mode"` key distinguishes
    `"per_row"` from `"per_table"`. Per-row's own `(scale, min_q)` pairs are
    *not* here — they travel inline with each `q_values` entry instead (see
    `q_value_entries_to_json`); this key only ever records that they should
    be expected there. See `quantization_from_json` for the inverse,
    including the backward-compat default a real PRD-12-era file (no
    `"mode"` key at all) relies on."""
    if quantization is None:
        return None
    if isinstance(quantization, PerRowQuantizationParams):
        return {"mode": "per_row", "dtype": quantization.dtype}
    return {
        "mode": "per_table",
        "dtype": quantization.dtype,
        "scale": quantization.scale,
        "min_q": quantization.min_q,
    }


def quantization_from_json(
    payload: dict, per_row_scales: dict[State, tuple[float, float]] | None = None
) -> QuantizationParams | PerRowQuantizationParams:
    """Inverse of `quantization_to_json`. `payload.get("mode", "per_table")`
    is exact backward compatibility, not a version branch: a real
    PRD-12-era file predates per-row mode entirely and was always
    per-table, so its absent `"mode"` key must default to that, never raise.
    `per_row_scales` — extracted by `q_value_entries_from_json` from the
    same `q_values` entries this checkpoint's `"quantization"` key refers
    to — is required, and only meaningful, for `"per_row"` mode."""
    if payload.get("mode", "per_table") == "per_row":
        return PerRowQuantizationParams(dtype=payload["dtype"], rows=per_row_scales or {})
    return QuantizationParams(dtype=payload["dtype"], scale=payload["scale"], min_q=payload["min_q"])


def q_value_entries_to_json(
    q_values: dict[State, dict[str, float]] | dict[State, dict[str, int]],
    quantization: QuantizationParams | PerRowQuantizationParams | None,
) -> list[dict]:
    """The `"q_values"` list `rl_checkpoint.py::save_checkpoint` writes
    as-is. Per-row mode inlines each state's own rounded `(scale, min_q)`
    into its own entry — see the module docstring for why."""
    if isinstance(quantization, PerRowQuantizationParams):
        entries = []
        for state, values in q_values.items():
            scale, min_q = quantization.rows[state]
            entries.append(
                {
                    "state": list(state),
                    "values": values,
                    "scale": round(scale, _ROW_PRECISION),
                    "min_q": round(min_q, _ROW_PRECISION),
                }
            )
        return entries
    return [{"state": list(state), "values": values} for state, values in q_values.items()]


def q_value_entries_from_json(
    entries: list[dict],
) -> tuple[dict[State, dict[str, Any]], dict[State, tuple[float, float]]]:
    """Inverse of `q_value_entries_to_json`: splits each entry back into
    its `(state -> values)` contribution (always present) and, only for
    entries that carry them, its `(state -> (scale, min_q))` contribution —
    empty for every non-per-row checkpoint, including every real
    PRD-11/12-era file, which never had these keys at all."""
    raw_values: dict[State, dict[str, Any]] = {}
    per_row_scales: dict[State, tuple[float, float]] = {}
    for entry in entries:
        state = tuple(entry["state"])
        raw_values[state] = entry["values"]
        if "scale" in entry:
            per_row_scales[state] = (entry["scale"], entry["min_q"])
    return raw_values, per_row_scales
