"""Rule 18 (**[FATAL]**): nonces must be cryptographically random, never
predictable — the test suite's own enforcement, not just a docstring claim.
"""

from __future__ import annotations

from pathlib import Path

from cop.integrity.nonce import generate_nonce


def test_generate_nonce_is_32_hex_characters():
    nonce = generate_nonce()
    assert len(nonce) == 32
    int(nonce, 16)  # raises ValueError if not valid hex


def test_two_calls_produce_different_values():
    assert generate_nonce() != generate_nonce()


def test_nonce_module_never_imports_random():
    """A real, automated rejection test for this specific module — not just
    a general repo-wide sweep — matching rule 18's own "from `secrets`,
    never `random`" wording exactly."""
    source = Path("src/cop/integrity/nonce.py").read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("import random")
        assert not stripped.startswith("from random")
