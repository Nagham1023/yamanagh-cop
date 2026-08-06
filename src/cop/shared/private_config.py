"""Loads the private, per-team `[trash_talk]` block (Table 21) — deliberately
a separate loader from `GameConfig.from_file`, not a shared dataclass.

Table 21/22 are explicit that this section is "private per peer, not
negotiated": it must never be diffed against the opponent's copy the way
`check_config.py --identical` diffs `GameConfig`. Keeping a distinct loader
(rather than folding these fields into `GameConfig`) is what keeps that
split real instead of just documented (PRD 4 Design Question 7).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PrivateConfig:
    provider: str
    every_n_steps: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PrivateConfig:
        provider = data["provider"]
        every_n_steps = data["every_n_steps"]
        if not isinstance(provider, str) or not provider:
            raise ValueError(f"provider must be a non-empty string, got {provider!r}")
        if (
            not isinstance(every_n_steps, int)
            or isinstance(every_n_steps, bool)
            or every_n_steps <= 0
        ):
            raise ValueError(f"every_n_steps must be a positive int, got {every_n_steps!r}")
        return cls(provider=provider, every_n_steps=every_n_steps)

    @classmethod
    def from_file(cls, path: str | Path) -> PrivateConfig:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw)
