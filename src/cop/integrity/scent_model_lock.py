"""Ch. 4.5's own negotiation ceremony, verbatim: "Before the series opens...
they must exchange the emission model and the decay model — in full,
including a concrete numeric example... and only then lock the agreement
cryptographically — e.g. a hash (SHA-256) of the agreed formula together
with the numeric example." Rule 23 (**[FATAL]**) is this hash.

Closes the gap `WIRE-CONTRACT.md`'s own ch. 4.5 section flagged as "still
not built": `integrity/step0.py::Step0Declaration` only ever carried
`config_sha256`, which locks the *numbers* (Table 16's `pheromone_*`
fields) but not the *formula shape* itself — two independently-written
implementations of `tau(t+1) = max(0,(1-rho)*tau(t)+delta_tau)` could still
drift on kernel layout or rounding while hashing identical config bytes.
This module hashes formula-shape-plus-numbers-plus-worked-example together,
exactly as ch. 4.5 asks.

The worked numeric example is *computed*, not hand-typed: it runs the real
`memory/scent.py::ScentField.advance()` twice on a synthetic board far
larger than any real `board_size` (so the kernel never clips against an
edge — the example is a pure function of `source_strength`/`decay_rate`
alone, independent of this particular match's board), so a future edit to
the real decay math is automatically reflected here rather than silently
drifting from a stale, hand-transcribed number.
"""

from __future__ import annotations

import hashlib

from ..domain.board import Board, Position
from ..memory.scent import ScentField
from ..shared.config import GameConfig
from .canonical_json import canonical_json_bytes

_VALUE_PRECISION = 10

# The fixed formula shape (ch. 4.3/Figure 4) — never a per-match value, so
# this string is the same for every config; it's part of what's hashed
# specifically so a peer running a differently-shaped formula (not just
# different numbers) produces a different hash too.
_FORMULA_DESCRIPTION = (
    "tau(t+1) = max(0, (1-rho)*tau(t) + delta_tau); "
    "delta_tau is a fixed radial 5x5 kernel (Figure 4) centered on the "
    "emitting cell, scaled by source_strength/0.9"
)

# Oversized purely so the kernel never clips against a board edge —
# this has no relationship to any real match's configured board_size.
# _FAR_CELL is more than one kernel radius (2) away from _SYNTHETIC_CENTER
# in both axes, so a deposit at one never touches the other's cell.
_SYNTHETIC_BOARD_SIZE = 9
_SYNTHETIC_CENTER = Position(4, 4)
_FAR_CELL = Position(0, 0)


def _worked_numeric_example(config: GameConfig) -> dict:
    """`WIRE-CONTRACT.md`'s own worked example (0.9 -> 0.81 under the
    default Table 16 numbers), reproduced by running the real
    `ScentField.advance()` rather than restated by hand: emit once at
    `_SYNTHETIC_CENTER`, then advance again at `_FAR_CELL` (far enough that
    its own fresh deposit never overlaps `_SYNTHETIC_CENTER`) so the second
    reading reflects pure decay of the first deposit, not decay-plus-a-new-
    deposit landing on the same cell."""
    board = Board(_SYNTHETIC_BOARD_SIZE)
    field = ScentField.from_config(config)
    field.advance(_SYNTHETIC_CENTER, board)
    center_after_emission = field.sample(_SYNTHETIC_CENTER, board)[_SYNTHETIC_CENTER]
    field.advance(_FAR_CELL, board)
    center_after_one_decay_round = field.sample(_SYNTHETIC_CENTER, board)[_SYNTHETIC_CENTER]
    return {
        "center_after_emission": f"{center_after_emission:.{_VALUE_PRECISION}f}",
        "center_after_one_decay_round": f"{center_after_one_decay_round:.{_VALUE_PRECISION}f}",
    }


def _canonical_scent_model_payload(config: GameConfig) -> dict:
    return {
        "formula_description": _FORMULA_DESCRIPTION,
        "source_strength": f"{config.scent_source_strength:.{_VALUE_PRECISION}f}",
        "decay_rate": f"{config.scent_decay_rate:.{_VALUE_PRECISION}f}",
        "field_size": config.scent_field_size,
        "worked_numeric_example": _worked_numeric_example(config),
    }


def compute_scent_model_hash(config: GameConfig) -> str:
    """SHA-256 of the canonical formula-shape + numbers + worked-example
    payload — this repo's own answer to ch. 4.5's "lock it cryptographically"
    instruction, exchanged as `Step0Declaration.scent_model_sha256`
    (`integrity/step0.py`) before move 1."""
    return hashlib.sha256(canonical_json_bytes(_canonical_scent_model_payload(config))).hexdigest()
