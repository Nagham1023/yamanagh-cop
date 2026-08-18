"""Operational event log — the Orchestrator's fifth wire (book Ch.8, Fig. 12).

Originally meant as a separate operational log distinct from PRD 6/7's
cryptographic replay artifact -- in practice this *is* the file
`cli_replay.py`/`ReplayViewer` reads (`event == "committing"` entries,
Table 20's own `log_<game_id>_g<NN>.json`), never a second, dedicated one.
Confirmed by reading `observability/replay_viewer.py` directly, not
assumed. This module exists so rule 7's "loss of the official record"
sanction has something to prevent: a deadline expiring or the watchdog
firing produces one real, readable line in a real file, not a print
statement that vanishes when the process dies -- and, since PRD 7 reuses
that same file, also the transcript rule 20's Replay Viewer verifies.

`Table 20`'s naming (`log_<game_id>_g<NN>.json`) is deterministic per
sub-game, not per attempt -- rerunning the same `sub_game_number` (a
warm-up redo, or a real sub-game restarted after a technical loss) reused
the same path with every prior attempt's own events still sitting in it,
`open(..., "a")` on every single `.log()` call, one real match log
silently mixing bytes from unrelated earlier runs. `__init__` now
truncates the file once, at construction -- the one point in this
object's life that legitimately means "a fresh match's own log starts
here" (`orchestrator.py` constructs exactly one `Trace` per process, per
match) -- so every `.log()` call within *that* match's own lifetime still
correctly appends, the property `test_log_appends_rather_than_overwrites`
proves, just never inheriting a dead attempt's leftover lines first."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class Trace:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("", encoding="utf-8")

    def log(self, event: str, **details: Any) -> None:
        """Append one JSON-line entry: `{"time": ..., "event": ..., **details}`."""
        entry = {"time": time.time(), "event": event, **details}
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
