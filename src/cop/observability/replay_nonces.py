"""`nonces_from_log` split out of `replay_viewer.py` once that file grew
past the 150-line house cap adding halt-on-tamper navigation — a single,
self-contained function with no other coupling to the `ReplayViewer`/
`ReplayViewerWindow` classes.
"""

from __future__ import annotations

import json
from pathlib import Path


def nonces_from_log(log_path: str | Path) -> dict[str, str]:
    """PRD 10: the only source of `nonces` a standalone `replay --log
    <path>` run has, once the process that played the match has already
    exited — `orchestrator_peer_audit.py::send_final_reveal_to_peer` logs
    a `nonces_revealed` event at the moment they stop being secret (rule
    18: *until* game end, not forever). Raises `ValueError` — not a crash,
    not a silent empty dict — when no such event exists: a crashed or
    otherwise incomplete match genuinely never revealed its nonces, and
    that is itself the honest, correct answer for a replay attempt against
    it, not a bug to paper over."""
    lines = Path(log_path).read_text(encoding="utf-8").splitlines()
    for line in reversed(lines):
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("event") == "nonces_revealed":
            return entry["nonces"]
    raise ValueError(
        f"{log_path}: no 'nonces_revealed' event found — this match never reached "
        f"Final Reveal, so its nonces were never (and should never be) recoverable"
    )
