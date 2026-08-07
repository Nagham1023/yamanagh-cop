"""Rule 19/23's audit half: a tampered scent map must fail
`verify_scent_map_against_commit` — the honest-path accept and the
tampered-path reject both tested, matching this project's own "write at
least one test per layer that proves rejection" rule (the old xfail guard
only ever tested the reject path with a placeholder hash).
"""

from __future__ import annotations

from cop.domain.board import Position
from cop.integrity.audit import verify_scent_map_against_commit
from cop.integrity.scent_commitment import commit_scent_map


def test_commit_is_deterministic_regardless_of_dict_insertion_order():
    a = {Position(1, 1): 0.9, Position(2, 2): 0.1}
    b = {Position(2, 2): 0.1, Position(1, 1): 0.9}
    assert commit_scent_map(a) == commit_scent_map(b)


def test_verify_accepts_a_genuine_field_against_its_own_commitment():
    field = {Position(2, 2): 0.9, Position(2, 1): 0.81}
    commit_hash = commit_scent_map(field)
    assert verify_scent_map_against_commit(field, commit_hash) is True


def test_verify_rejects_a_tampered_field():
    genuine_field = {Position(2, 2): 0.9}
    commit_hash = commit_scent_map(genuine_field)
    tampered_field = {Position(6, 6): 0.9}
    assert verify_scent_map_against_commit(tampered_field, commit_hash) is False


def test_verify_rejects_a_field_with_one_value_perturbed():
    genuine_field = {Position(2, 2): 0.9}
    commit_hash = commit_scent_map(genuine_field)
    perturbed_field = {Position(2, 2): 0.90000001}
    assert verify_scent_map_against_commit(perturbed_field, commit_hash) is False


def test_empty_scent_field_still_commits_and_verifies():
    commit_hash = commit_scent_map({})
    assert verify_scent_map_against_commit({}, commit_hash) is True
