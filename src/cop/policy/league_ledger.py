"""Game-count bookkeeping rules 31/37/38/52 require: which opponents this
team has already played a *counted* game against, how many counted games
total. File-backed (not in-memory-only) — a real series against one
opponent (Table 18's `num_games`, six sub-games) spans multiple process
lifetimes (one `Orchestrator` per sub-game), so the count must survive a
restart between games, unlike `_pending_nonces`'s own single-turn lifetime.

Warm-ups (ch. 9.2.1: permitted, not counted) are never recorded here at
all — this ledger only ever tracks *counted* games, matching rule 52's own
scope exactly.

Honest-by-construction only (same category as `Intent`'s honesty since
PRD 4): nothing prevents this repo's own process from simply not calling
`record_counted_game`, or calling it with a fabricated `opponent_id`. The
real enforcement is the end-of-series mutual reconciliation the lecturer
performs across both sides' independent reports (ch. 9.2.1's own "not a
matter of trust" framing) — this ledger's job is to make the *truthful*
path the easy, natural one to take, and to refuse the one thing it *can*
enforce locally: rule 52's one-counted-game-per-opponent limit.
"""

from __future__ import annotations

import json
from pathlib import Path

_DEFAULT_PATH = "logs/league_ledger.json"


class LeagueLedger:
    def __init__(self, path: str | Path = _DEFAULT_PATH) -> None:
        self._path = Path(path)
        self._counted_opponents: set[str] = self._load()

    def _load(self) -> set[str]:
        if not self._path.exists():
            return set()
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return set(data["counted_opponents"])

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"counted_opponents": sorted(self._counted_opponents)}
        self._path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def is_already_counted(self, opponent_id: str) -> bool:
        return opponent_id in self._counted_opponents

    def record_counted_game(self, opponent_id: str) -> None:
        """Rule 52 (**[FATAL]**): one counted game per opponent. Raises
        rather than silently no-op'ing on a repeat — a repeat opponent
        being marked counted twice is exactly the violation this rule
        exists to prevent, not a harmless duplicate."""
        if self.is_already_counted(opponent_id):
            raise ValueError(
                f"opponent {opponent_id!r} already has a counted game — "
                "rule 52 [FATAL]: one counted game per opponent"
            )
        self._counted_opponents.add(opponent_id)
        self._save()

    def counted_game_count(self) -> int:
        return len(self._counted_opponents)

    def declare_at_game_start(self) -> int:
        """Rule 37: the truthful count to put in the declaration file —
        just `counted_game_count()`, named for the call site's own purpose
        rather than making every caller re-derive that mapping."""
        return self.counted_game_count()
