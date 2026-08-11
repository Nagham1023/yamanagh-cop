"""checkpoint_io.save(): the training-side handoff into rl_checkpoint's format."""

from __future__ import annotations

from cop.reasoning.rl_checkpoint import load_checkpoint
from training.checkpoint_io import save
from training.q_table import QTable


def test_save_round_trips_through_the_production_loader(tmp_path):
    table = QTable()
    table.update((1, 2, 0), "N", 4.5)
    path = tmp_path / "checkpoint.json"

    save(path, table)

    loaded = load_checkpoint(path)
    assert loaded.ranked_actions((1, 2, 0)) == ["N"]


def test_save_of_an_empty_table_produces_a_loadable_checkpoint_with_all_misses(tmp_path):
    path = tmp_path / "checkpoint.json"
    save(path, QTable())
    loaded = load_checkpoint(path)
    assert loaded.ranked_actions((0, 0, 0)) is None
