"""Training-side wrapper around `cop.reasoning.rl_checkpoint`'s save/load —
keeps `train_loop.py`/callers from needing to know the checkpoint file
format directly, and is the one place training converts its own mutable
`QTable` into the plain-dict shape the production module's `save_checkpoint`
expects.
"""

from __future__ import annotations

from pathlib import Path

from cop.reasoning.rl_checkpoint import save_checkpoint

from .q_table import QTable


def save(path: str | Path, q_table: QTable) -> None:
    save_checkpoint(path, q_table.as_dict())
