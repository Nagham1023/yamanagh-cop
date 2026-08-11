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
from .quantize import quantize_q_table


def save(path: str | Path, q_table: QTable) -> None:
    save_checkpoint(path, q_table.as_dict())


def save_quantized(path: str | Path, q_table: QTable) -> None:
    """PRD 12: quantizes before writing — `load_checkpoint` dequantizes
    transparently, so `RLCopBrain` needs no code path change either way."""
    quantized, params = quantize_q_table(q_table.as_dict())
    save_checkpoint(path, quantized, quantization=params)
