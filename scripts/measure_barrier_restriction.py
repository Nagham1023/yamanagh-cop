"""Report whether a trained Q-table's own barrier-placement choices already
restrict the believed target's escape routes — the real measurement that
decides whether a new belief-aware reward-shaping term (PRD 14 post-gate
follow-up) is warranted at all. See
`training/pipeline/barrier_restriction_metric.py`'s own module docstring
for why this is measured before any such term is written.

Run:
    uv run python scripts/measure_barrier_restriction.py [checkpoint_path]
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from cop.reasoning.rl_checkpoint import load_checkpoint  # noqa: E402
from training.pipeline import barrier_restriction_metric  # noqa: E402

_DEFAULT_CHECKPOINT = "training/runs/prd14_gate_candidate_round1/checkpoint.json"

if __name__ == "__main__":
    checkpoint_path = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_CHECKPOINT
    table = load_checkpoint(checkpoint_path)
    result = barrier_restriction_metric.measure_barrier_restriction_rate(table.as_dict())

    print(f"checkpoint: {checkpoint_path}")
    print(f"states where a barrier is the top-ranked action: {result['barrier_top_states']}")
    print(f"  of those, restricting the believed target's escape routes: {result['restricting']}")
    fraction = result["fraction_restricting"]
    if fraction is None:
        print("fraction_restricting: N/A (no state ever top-ranks a barrier)")
    else:
        print(f"fraction_restricting: {fraction:.4f} ({fraction * 100:.1f}%)")
