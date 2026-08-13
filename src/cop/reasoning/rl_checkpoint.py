"""RLCheckpoint: canonical JSON format for a trained Q-table (PRD 11).

Shared by training (write, via `training/checkpoint_io.py`) and inference
(read, via `RLCopBrain`) — putting the canonical format here, in the
production module, and having `training/` import it one-way, avoids a
two-copies-drift bug class this repo already hit once (the belief-target
seam that motivated `reasoning/state.py::ground_truth_target_position`).

`RLQTable` is deliberately a separate, smaller class from training's own
mutable `QTable` (`training/q_table.py`): inference only ever needs a
read-only ranked lookup, never an update — conflating the two would import
`training/` into `src/cop/`, which is exactly the boundary
`tests/unit/test_training_boundary.py` exists to keep closed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .rl_checkpoint_json import (
    q_value_entries_from_json,
    q_value_entries_to_json,
    quantization_from_json,
    quantization_to_json,
)
from .rl_checkpoint_quant import PerRowQuantizationParams, QuantizationParams, dequantize_any
from .rl_state_encoding import State

_CURRENT_ENCODING_VERSION = "v5"  # PRD 14 round-2 post-gate: State grew from a 6-tuple to an 8-tuple (dx2, dy2 -- an optional second belief mode) -- a real shape change this time, not just a semantic one like v3->v4; a stale v4 file (correct old shape) must fail closed too, not be silently misread as having two extra trailing fields


class RLQTable:
    """Read-only, inference-side view of a trained Q-table."""

    def __init__(self, values: dict[State, dict[str, float]]) -> None:
        """`values` is already-loaded, already-validated checkpoint data —
        `load_checkpoint` is the only intended caller."""
        self._values = values

    def ranked_actions(self, state: State) -> list[str] | None:
        """Actions at `state`, best Q-value first — or `None` on a miss
        (an unvisited state), which `RLCopBrain` treats as "fall back to
        the heuristic," never as "guess."""
        row = self._values.get(state)
        if row is None:
            return None
        return sorted(row, key=row.__getitem__, reverse=True)

    def as_dict(self) -> dict[State, dict[str, float]]:
        """Already-dequantized real floats regardless of the checkpoint's
        own on-disk format — PRD 13's pipeline uses this to re-quantize (or
        re-benchmark) a checkpoint independently of the process that
        trained it, without caring whether it loaded a PRD-11 or PRD-12 file."""
        return dict(self._values)


def save_checkpoint(
    path: str | Path,
    q_values: dict[State, dict[str, float]] | dict[State, dict[str, int]],
    *,
    state_encoding_version: str = _CURRENT_ENCODING_VERSION,
    quantization: QuantizationParams | PerRowQuantizationParams | None = None,
) -> None:
    """`q_values` is a plain dict (`training/q_table.py::QTable.as_dict()`'s
    output, or one of `training/quantize.py`'s two `quantize_q_table*`
    outputs when `quantization` is given) — this function never depends on
    training's own `QTable` class. `quantization=None` (the PRD 11 shape)
    means `q_values` are already the real floats; either quantization params
    type means they are int codes `load_checkpoint` must dequantize.

    A `"mode"` key inside `"quantization"` distinguishes the two
    (`"per_row"` vs. `"per_table"`) — see `load_checkpoint`'s own
    backward-compat handling of a file with no `"mode"` key at all (a real
    PRD-12-era file, always per-table)."""
    payload: dict[str, Any] = {
        "state_encoding_version": state_encoding_version,
        "quantization": quantization_to_json(quantization),
        "q_values": q_value_entries_to_json(q_values, quantization),
    }
    Path(path).write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


def load_checkpoint(path: str | Path) -> RLQTable:
    """Raises `ValueError` on a malformed/corrupted file rather than
    returning a partial table silently — a broken checkpoint reaching a
    real match undetected is worse than a loud failure at load time.

    A PRD-11-era checkpoint (no `quantization` key at all) loads exactly as
    before — backward compatible by construction, not by a version branch:
    `raw.get("quantization")` is `None` either way."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        raw: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"corrupted RL checkpoint at {path}: not valid JSON") from exc

    if not isinstance(raw, dict) or "q_values" not in raw or "state_encoding_version" not in raw:
        raise ValueError(f"corrupted or unrecognized RL checkpoint at {path}")
    if raw["state_encoding_version"] != _CURRENT_ENCODING_VERSION:
        raise ValueError(
            f"checkpoint at {path} uses state_encoding_version="
            f"{raw['state_encoding_version']!r}, this build expects "
            f"{_CURRENT_ENCODING_VERSION!r}"
        )

    raw_values, per_row_scales = q_value_entries_from_json(raw["q_values"])

    quantization = raw.get("quantization")
    if quantization is None:
        return RLQTable(raw_values)
    params = quantization_from_json(quantization, per_row_scales)
    return RLQTable(dequantize_any(raw_values, params))
