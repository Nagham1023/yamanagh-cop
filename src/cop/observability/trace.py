"""Operational event log — the Orchestrator's fifth wire (book Ch.8, Fig. 12).

This is **not** the cryptographic, Commit-Reveal-backed match-replay log
that PRD 6 (audit, rule 19) and PRD 7 (Replay app, rule 20) build — that's a
different and much heavier artifact, still out of scope here. This module
exists solely so rule 7's "loss of the official record" sanction has
something to prevent in PRD 2: a deadline expiring or the watchdog firing
produces one real, readable line in a real file, not just a print statement
that vanishes when the process dies.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class Trace:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **details: Any) -> None:
        """Append one JSON-line entry: `{"time": ..., "event": ..., **details}`."""
        entry = {"time": time.time(), "event": event, **details}
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
