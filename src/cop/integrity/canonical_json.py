"""Canonical JSON encoding shared by every `integrity/` module that hashes a
payload (`commit_payload.py`, `commit_reveal.py`, `step0.py`) — `sort_keys`
plus a compact separator so two independently-constructed payloads with the
same logical content always hash to the same bytes, regardless of dict
insertion order or incidental whitespace. Extracted to its own module,
rather than left as `commit_payload.py`'s own private constant, once a
second module (`commit_reveal.py`, PRD 6) needed the exact same encoding —
duplicating it would let the two drift apart silently.
"""

from __future__ import annotations

import json

CANONICAL_JSON_KWARGS = {"sort_keys": True, "separators": (",", ":")}


def canonical_json_bytes(payload: object) -> bytes:
    """UTF-8-encoded canonical JSON — the exact bytes every `commit()`/
    `sign_*()` function in `integrity/` hashes."""
    return json.dumps(payload, **CANONICAL_JSON_KWARGS).encode("utf-8")
