"""Report how many visited states landed in each entropy bucket of a real
trained checkpoint — confirms Shannon-entropy bucketing (PRD 14 post-gate
follow-up) actually discriminates real training data into all 3 buckets,
not silently collapsing them into one or two.

Run:
    uv run python scripts/measure_entropy_bucket_coverage.py [checkpoint_path]
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from cop.reasoning.rl_checkpoint import load_checkpoint  # noqa: E402

_DEFAULT_CHECKPOINT = "training/runs/prd14_gate_candidate_round1/checkpoint.json"
_BUCKET_LABELS = {0: "high ambiguity", 1: "medium", 2: "high certainty"}

if __name__ == "__main__":
    checkpoint_path = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_CHECKPOINT
    table = load_checkpoint(checkpoint_path)
    q_values = table.as_dict()

    counts = Counter(state[3] for state in q_values)
    total = len(q_values)

    print(f"checkpoint: {checkpoint_path}")
    print(f"total states visited: {total}")
    for bucket in (0, 1, 2):
        count = counts.get(bucket, 0)
        fraction = count / total if total else 0.0
        label = _BUCKET_LABELS[bucket]
        print(f"  bucket {bucket} ({label}): {count} ({fraction * 100:.1f}%)")
