"""Rule 23 (**[FATAL]**): the ch. 4.5 scent-model lock. `config` is the
shared fixture in `conftest.py` (`scent_source_strength=0.9`,
`scent_decay_rate=0.10`, matching `WIRE-CONTRACT.md`'s own worked example).
"""

from __future__ import annotations

import dataclasses

from cop.integrity.scent_model_lock import _worked_numeric_example, compute_scent_model_hash


def test_worked_numeric_example_matches_wire_contracts_own_documented_values(config):
    example = _worked_numeric_example(config)
    assert example["center_after_emission"] == "0.9000000000"
    assert example["center_after_one_decay_round"] == "0.8100000000"


def test_compute_scent_model_hash_is_deterministic(config):
    assert compute_scent_model_hash(config) == compute_scent_model_hash(config)


def test_compute_scent_model_hash_changes_when_decay_rate_differs(config):
    other = dataclasses.replace(config, scent_decay_rate=0.25)
    assert compute_scent_model_hash(config) != compute_scent_model_hash(other)


def test_compute_scent_model_hash_changes_when_source_strength_differs(config):
    other = dataclasses.replace(config, scent_source_strength=0.5)
    assert compute_scent_model_hash(config) != compute_scent_model_hash(other)


def test_compute_scent_model_hash_unaffected_by_unrelated_config_fields(config):
    """The scent-model lock is scoped to the formula/numbers ch. 4.5 asks
    for — not a restatement of `config_sha256`, which already covers the
    whole file. A field with no bearing on the scent formula (e.g. the
    barrier quota) must not perturb this hash."""
    other = dataclasses.replace(config, barrier_quota=1)
    assert compute_scent_model_hash(config) == compute_scent_model_hash(other)
