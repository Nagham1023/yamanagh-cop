"""Nonce generation for PRD 6 Commit-Reveal (rule 18, **[FATAL]**): every
nonce must come from `secrets`, never `random` — a nonce predictable from a
seed defeats the entire commit-reveal scheme, since it would let an
adversary brute-force candidate `(State, Move, Intent)` triples against a
committed hash before the reveal actually happens. One function, on
purpose: exists so nothing else anywhere in `integrity/` reaches for
`random` or hand-rolls hex generation.
"""

from __future__ import annotations

import secrets


def generate_nonce() -> str:
    """A fresh, cryptographically random 128-bit nonce, hex-encoded."""
    return secrets.token_hex(16)
