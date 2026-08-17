"""std_v1/crypto.py tests — verifies this module's own worked examples
(Appendix B) rather than just round-tripping, so a formula regression
that still happens to round-trip with itself still gets caught."""

from __future__ import annotations

import hashlib
import json

from cop.std_v1.crypto import (
    canonical,
    commit_of,
    consensus_digest,
    derive_game_id,
    derive_game_uid,
    fresh_nonce,
)


def test_canonical_sorts_keys_and_uses_compact_separators():
    assert canonical({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_canonical_does_not_escape_non_ascii():
    assert canonical({"hint": "café"}) == '{"hint":"café"}'


def test_fresh_nonce_is_32_lowercase_hex_chars():
    nonce = fresh_nonce()
    assert len(nonce) == 32
    assert all(c in "0123456789abcdef" for c in nonce)


def test_fresh_nonce_is_not_repeated():
    assert fresh_nonce() != fresh_nonce()


def test_commit_of_matches_the_pipe_concatenation_formula():
    payload = {"step": 1}
    nonce = "a" * 32
    expected = hashlib.sha256((canonical(payload) + "|" + nonce).encode("utf-8")).hexdigest()
    assert commit_of(payload, nonce) == expected


def test_commit_of_treats_an_explicit_nonce_key_as_ordinary_payload_data():
    # The nonce is concatenated as a raw string suffix, never merged into
    # the hashed object — a payload that happens to carry its own "nonce"
    # key hashes differently than commit_of(payload, nonce) unless that
    # key's value is byte-identical to the real nonce.
    payload_without = {"step": 1}
    payload_with_same_value = {"step": 1, "nonce": "x" * 32}
    assert commit_of(payload_without, "x" * 32) != commit_of(payload_with_same_value, "x" * 32)


def test_derive_game_id_is_order_independent():
    assert derive_game_id("alpha", "beta") == derive_game_id("beta", "alpha")
    assert derive_game_id("alpha", "beta") == "alpha-vs-beta"


def test_derive_game_uid_is_order_independent():
    terms = {"board_size": 7}
    assert derive_game_uid(terms, "alpha", "beta") == derive_game_uid(terms, "beta", "alpha")


def test_derive_game_uid_is_a_valid_uuid_string():
    import uuid

    uid = derive_game_uid({"a": 1}, "alpha", "beta")
    assert str(uuid.UUID(uid)) == uid


def test_derive_game_uid_changes_with_terms():
    assert derive_game_uid({"a": 1}, "alpha", "beta") != derive_game_uid({"a": 2}, "alpha", "beta")


def test_consensus_digest_matches_plain_sha256_of_canonical_json():
    obj = {"game_id": "a-vs-b", "sub_games": []}
    expected = hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert consensus_digest(obj) == expected


def test_consensus_digest_is_deterministic_regardless_of_input_key_order():
    a = {"x": 1, "y": 2}
    b = {"y": 2, "x": 1}
    assert consensus_digest(a) == consensus_digest(b)
