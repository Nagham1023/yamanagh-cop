"""Optional scent-model declaration, riding as a negotiate extra alongside
the required Section-3 fields (never inside the closed 14-key `terms`
set, and never inside `identity`'s Section-12-report-bound fields --
`report.py::group_details` only ever whitelists specific keys off
`identity`, so an extra key there is invisible to the submitted report,
by construction).

This is *not* required by the Guide (`docs/NEXT_OPPONENT_INTEROP_GUIDE_
PUBLIC.md`) -- Appendix E already fixes the scent formula and its four
signed terms (`smell_grid_size`, `decay_per_step`, `emit_intensity`,
`min_center_intensity`) cover the numbers; scent/hints are explicitly
[LOCAL] there (capture is always coordinate-only, never scent-derived).
It exists to interoperate with a second real opponent's own conformance
kit (github.com/Imreec/copthief-league-protocol, see docs/
IMREEC_LEAGUE_KIT_COMPAT.md), which registers two named scent models
(the book's own fixed multiplicative kernel, and a "reference"
subtractive-Chebyshev alternative) and refuses a handshake only when
*both* peers declare a model and disagree -- so sending this is a
strictly additive, never-required declaration: an old peer that doesn't
recognise it simply never looks at it (`validate_offer` only reads
specific known keys, never rejects a message for extra ones -- see
handshake.py).

Mirrors `thief-peer`'s own `interop/std_v1/scent_model_lock.py` bit-for-
bit (same family/name/kernel/formula/key shapes) so the two repos'
declarations are consistent, not just individually well-formed. The
worked example is *computed*, not hand-typed, by running the real
`memory/scent.py::ScentField.advance()` on a synthetic, oversized board
-- the same technique this repo's own `integrity/scent_model_lock.py`
already uses for the native protocol's ch.4.5 ceremony -- so a future
change to the real decay math is automatically reflected here instead of
silently drifting from a stale, hand-transcribed number.
"""

from __future__ import annotations

import hashlib

from ..domain.board import Board, Position
from ..memory.scent import ScentField
from .crypto import canonical

_FAMILY = "scent_model"
_NAME = "multiplicative_book_v1"
_FORMULA = "tau_next = min(cap, max(0, (1 - decay_per_step) * tau_old + delta))"

# Figure 4 / Appendix E's own kernel, keyed the same "r,c" way the wire's
# smell_grid field is -- offsets relative to the emitting cell.
_KERNEL_OFFSETS = {
    "0,0": 0.90, "0,1": 0.62, "1,0": 0.62, "1,1": 0.42,
    "0,2": 0.20, "2,0": 0.20, "1,2": 0.14, "2,1": 0.14, "2,2": 0.04,
}  # fmt: skip

# Oversized purely so the kernel (radius 2) never clips against a board
# edge and the two synthetic cells never overlap each other's deposit --
# unrelated to any real match's configured board_size.
_SYNTHETIC_BOARD_SIZE = 9
_SYNTHETIC_CENTER = Position(4, 4)
_FAR_CELL = Position(0, 0)


def _worked_example(emit_intensity: float, decay_per_step: float) -> dict:
    board = Board(_SYNTHETIC_BOARD_SIZE)
    field = ScentField(source_strength=emit_intensity, decay_rate=decay_per_step, window_size=5)
    field.advance(_SYNTHETIC_CENTER, board)
    tau_before = field.sample(_SYNTHETIC_CENTER, board)[_SYNTHETIC_CENTER]
    field.advance(_FAR_CELL, board)  # far enough away: the centre only decays now
    tau_after = field.sample(_SYNTHETIC_CENTER, board)[_SYNTHETIC_CENTER]
    return {"tau_before": tau_before, "tau_after": tau_after}


def build_scent_model_lock(terms: dict) -> dict:
    """Returns the Imreec-kit-shaped locked-model declaration for this
    repo's own scent implementation, plus its sha256 -- computed from the
    *real* signed terms (`emit_intensity`, `decay_per_step`), never a
    hardcoded 0.9/0.1."""
    emit_intensity = terms["emit_intensity"]
    decay_per_step = terms["decay_per_step"]
    doc = {
        "family": _FAMILY,
        "name": _NAME,
        "params": {
            "emit_intensity": emit_intensity,
            "decay_per_step": decay_per_step,
            "cap": emit_intensity,
            "kernel": _KERNEL_OFFSETS,
            "formula": _FORMULA,
        },
        "example": _worked_example(emit_intensity, decay_per_step),
    }
    sha256 = hashlib.sha256(canonical(doc).encode("utf-8")).hexdigest()
    return {**doc, "sha256": sha256}
