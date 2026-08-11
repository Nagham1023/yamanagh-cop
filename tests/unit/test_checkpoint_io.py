"""checkpoint_io.save(): the training-side handoff into rl_checkpoint's format."""

from __future__ import annotations

from cop.reasoning.rl_checkpoint import load_checkpoint
from training.checkpoint_io import save, save_quantized
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


def test_save_quantized_round_trips_and_preserves_ranking(tmp_path):
    table = QTable()
    table.update((0, 0, 0), "N", 10.0)
    table.update((0, 0, 0), "E", -10.0)
    path = tmp_path / "checkpoint.json"

    save_quantized(path, table)

    loaded = load_checkpoint(path)
    assert loaded.ranked_actions((0, 0, 0)) == ["N", "E"]


def test_save_quantized_file_is_smaller_than_the_float_original_for_a_larger_table(tmp_path):
    table = QTable()
    for i in range(200):
        table.update((i, 0, 0), "N", i / 3.0)  # non-round floats, worst case for JSON size
    float_path = tmp_path / "float.json"
    quantized_path = tmp_path / "quantized.json"

    save(float_path, table)
    save_quantized(quantized_path, table)

    assert quantized_path.stat().st_size < float_path.stat().st_size
