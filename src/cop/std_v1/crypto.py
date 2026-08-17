"""Cryptographic derivations, transcribed exactly from the spec's own
Appendix B pseudocode. A dedicated implementation, not a reuse of
`integrity/commit_reveal.py`/`integrity/canonical_json.py` — the two
schemes differ in real, breaking ways: this spec's `commit_of`
concatenates `canonical(payload) + "|" + nonce` as a plain string (the
nonce never enters the hashed JSON at all), while this repo's own
book-formula embeds the nonce inside the hashed object instead. Reusing
either implementation for the other's job would silently produce the
wrong bytes on the wire — this file is intentionally byte-for-bit
identical to `thief_peer.interop.std_v1.crypto` (the paired Thief repo),
verified against the same worked examples during joint testing.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid


def canonical(obj: object) -> str:
    """The spec's one canonical form, used for every hash and signature.
    `ensure_ascii=False` is required explicitly by the spec — a non-ASCII
    hint or member name would canonicalize to different bytes on each
    side without it."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def fresh_nonce() -> str:
    """A fresh 32-hex-char nonce from `secrets` (rule 18 — never `random`),
    matching `NONCE_HEX_CHARS = 32` in the spec's own worked examples."""
    return secrets.token_hex(16)


def commit_of(payload: dict, nonce: str) -> str:
    """SHA-256 over `canonical(payload) + "|" + nonce` — never over a JSON
    object containing the nonce."""
    material = canonical(payload) + "|" + nonce
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def derive_game_id(group_a: str, group_b: str) -> str:
    """Order-independent: both peers compute the identical id regardless
    of which side is "local" — the two group ids sorted, joined by the
    literal string `"-vs-"`."""
    return "-vs-".join(sorted([group_a, group_b]))


def derive_game_uid(terms: dict, group_a: str, group_b: str) -> str:
    """A UUID built from the first 16 raw bytes (not hex) of a SHA-256
    over `canonical(terms) + "|"` + the two sorted group ids joined by
    `"|"` — order-independent for the same reason `derive_game_id` is."""
    pair = sorted([group_a, group_b])
    seed = canonical(terms) + "|" + "|".join(pair)
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return str(uuid.UUID(bytes=digest[:16]))


def consensus_digest(consensus_obj: dict) -> str:
    """SHA-256 hex digest over the canonical Section-11 consensus object —
    the one value both peers must agree on bit-for-bit at series end."""
    return hashlib.sha256(canonical(consensus_obj).encode("utf-8")).hexdigest()
