"""Cryptographically locks a scent-map snapshot (rule 19/23's audit half) —
closes the gap `PRD-4-language-and-scent.md` "Revision 3" flagged when
`share_scent_map()` became a Tool returning structured numeric data:
honest-by-construction only, no cryptographic check that the returned field
genuinely matches the sender's actual `ScentField` state.

Two traps `commit_payload.py`'s own float discipline already exists to
close, both apply here too: a `dict`'s iteration order isn't something to
hash directly (sorted explicitly by `(col, row)`, same as
`canonical_state_bytes`'s sorted `barriers_placed`), and a raw float in the
hashed payload is a latent cross-recomputation mismatch (fixed-precision
string, same "if a float has to be in there" mitigation
`step0.py`/`PRD-6-prep-commit-payload-spec.md` already use).
"""

from __future__ import annotations

import hashlib
import secrets

from ..domain.board import Position
from .canonical_json import canonical_json_bytes

_VALUE_PRECISION = 10


def _canonical_scent_payload(scent_data: dict[Position, float]) -> dict:
    cells = sorted(
        ([pos.col, pos.row, f"{value:.{_VALUE_PRECISION}f}"] for pos, value in scent_data.items()),
        key=lambda triple: (triple[0], triple[1]),
    )
    return {"cells": cells}


def commit_scent_map(scent_data: dict[Position, float]) -> str:
    """SHA-256 of the scent field's canonical form — computed once, at
    `share_scent_map()` time, and logged for later audit."""
    return hashlib.sha256(canonical_json_bytes(_canonical_scent_payload(scent_data))).hexdigest()


def verify_scent_map_against_commit(claimed_field: dict[Position, float], commit_hash: str) -> bool:
    """Re-serializes `claimed_field` the same canonical way and compares
    hashes (`secrets.compare_digest`, never a float-by-float comparison) —
    re-exported from `integrity/audit.py` (its own required home) rather
    than defined twice."""
    return secrets.compare_digest(commit_scent_map(claimed_field), commit_hash)
