"""Loads the private, per-team `config/game.toml` — deliberately a separate
loader from `GameConfig.from_file`, not a shared dataclass.

Table 21/22 are explicit that this whole file is "private per peer, not
negotiated": it must never be diffed against the opponent's copy the way
`check_config.py --identical` diffs `GameConfig`. Keeping a distinct loader
(rather than folding these fields into `GameConfig`) is what keeps that
split real instead of just documented (PRD 4 Design Question 7).

`todoFullFix.md` §B: the book's actual private file (p.130-132) is TOML —
`config/game.toml`, six sections (`[game]`/`[network]`/`[strategy]`/
`[trash_talk]`/`[llm]`/`[email]`) — not the flat, JSON, `[trash_talk]`-only
shape earlier PRDs built. `opponent_url` lives in `[network]` here — "the
only thing I know about the opponent" (the book's own words) — which is
also why it belongs in this never-negotiated, never-hashed file rather than
as a runtime-only argument. `[strategy]` is read but not yet consumed
anywhere (PRD 4's "Explicitly out of scope" note still applies; dynamic
`thief_class`/`police_class` loading is unbuilt).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PrivateConfig:
    provider: str
    every_n_steps: int
    opponent_url: str
    my_port: int
    turn_timeout_seconds: float
    group_name: str
    group_id: str
    sub_game_number: int
    members: tuple[str, ...]
    repos: dict[str, str]
    model: str
    step_deadline_seconds: float
    email_recipient: str
    email_mode: str
    thief_class: str | None = None
    police_class: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PrivateConfig:
        game = data["game"]
        network = data["network"]
        trash_talk = data["trash_talk"]
        llm = data["llm"]
        email = data["email"]
        strategy = data.get("strategy", {})

        provider = trash_talk["provider"]
        every_n_steps = trash_talk["every_n_steps"]
        if not isinstance(provider, str) or not provider:
            raise ValueError(f"provider must be a non-empty string, got {provider!r}")
        if (
            not isinstance(every_n_steps, int)
            or isinstance(every_n_steps, bool)
            or every_n_steps <= 0
        ):
            raise ValueError(f"every_n_steps must be a positive int, got {every_n_steps!r}")

        return cls(
            provider=provider,
            every_n_steps=every_n_steps,
            opponent_url=network["opponent_url"],
            my_port=network["my_port"],
            turn_timeout_seconds=float(network["turn_timeout_seconds"]),
            group_name=game["group_name"],
            group_id=game["group_id"],
            sub_game_number=game["sub_game_number"],
            members=tuple(game["members"]),
            repos=dict(game["repos"]),
            model=llm["model"],
            step_deadline_seconds=float(llm["step_deadline_seconds"]),
            email_recipient=email["recipient"],
            email_mode=email["mode"],
            thief_class=strategy.get("thief_class"),
            police_class=strategy.get("police_class"),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> PrivateConfig:
        raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw)
