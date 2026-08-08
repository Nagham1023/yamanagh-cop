"""Token-total aggregation (rule 54) — reads the trace log's own per-turn
`tokens_used` field (`orchestrator_turn.py`'s `hint_generated` event) and
rolls it up. Honestly `0` under `template`/`ollama` (Table 21's own
zero-token modes, the only implemented providers) — rule 54 requires
reporting *actual* consumption, not requiring non-zero consumption.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TokenTotals:
    total_tokens: int = 0
    turns_counted: int = 0


def aggregate_tokens(trace_log_path: str | Path) -> TokenTotals:
    total = 0
    count = 0
    for line in Path(trace_log_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("event") == "hint_generated":
            total += entry.get("tokens_used", 0)
            count += 1
    return TokenTotals(total_tokens=total, turns_counted=count)
