"""Report what fraction of visited states in a real trained checkpoint have
a genuine second belief mode (PRD 14 round-2 post-gate) — confirms
`second_mode()`'s `min_separation`/`min_relative_mass` thresholds actually
fire often enough to be a meaningful state feature, not dead code that
never triggers. A near-zero result means the thresholds need loosening.

Run:
    uv run python scripts/measure_bimodal_coverage.py [checkpoint_path]
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from cop.reasoning.rl_checkpoint import load_checkpoint  # noqa: E402

_DEFAULT_CHECKPOINT = "training/runs/prd14_gate_candidate_round1/checkpoint.json"

if __name__ == "__main__":
    checkpoint_path = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_CHECKPOINT
    table = load_checkpoint(checkpoint_path)
    q_values = table.as_dict()

    total = len(q_values)
    bimodal_count = sum(1 for state in q_values if state[6:8] != (0, 0))
    fraction = bimodal_count / total if total else 0.0

    print(f"checkpoint: {checkpoint_path}")
    print(f"total states visited: {total}")
    print(f"states with a genuine second belief mode: {bimodal_count} ({fraction * 100:.1f}%)")
