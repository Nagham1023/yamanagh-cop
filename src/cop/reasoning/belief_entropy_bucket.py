"""Shannon-entropy confidence bucketing (PRD 14 post-gate follow-up),
extracted from `rl_state_encoding.py` up front to keep that file under the
150-line house cap once this landed — also legitimizes a real pre-existing
smell: `hybrid_cop_brain.py` previously reached into `rl_state_encoding.py`'s
underscore-prefixed "private" names across a module boundary; both now
import a shared, deliberately-public module instead.

Replaces the earlier max-probability bucketing (`_bucket_confidence`) with
one driven by `BeliefMap.entropy()` — entropy captures how "modal" a
distribution is far better than a single peak-probability reading: two
distributions can share the same peak probability while one is a clean
single mode and the other is split evenly across several, and only entropy
tells them apart.

3 buckets, not the old 4 (`ENTROPY_THRESHOLDS` has 2 elements where
`rl_checkpoint`'s prior `_CONFIDENCE_THRESHOLDS` had 3) — a deliberate
granularity reduction matching the exact 3 named buckets (High Certainty /
Medium / High Ambiguity) this session's proposal specified.

Natural log (nats) throughout, not log2: a uniform 7x7=49-cell prior's max
entropy is `ln(49)~=3.892`; the thresholds below sit at ~1/4 and ~2/3 of
that — clean, plausible fractions. `log2`'s own max (~5.615) fits the same
thresholds less naturally. This repo's own tuning choice either way (I6
doesn't apply — algorithm constant, same category as `_CLAMP_RADIUS`).
"""

from __future__ import annotations

ENTROPY_THRESHOLDS = (1.0, 2.5)  # natural log (nats); ~1/4 and ~2/3 of ln(49)


def bucket_entropy(entropy: float) -> int:
    """Higher bucket index = MORE certain (lower entropy) — the direct
    inversion of the prior probability-based bucketing's own structure
    (start at the top bucket, step down once per threshold crossed, return
    as soon as one isn't), so `HybridCopBrain`'s `>= len(ENTROPY_THRESHOLDS)`
    "top bucket" check keeps meaning "confident enough to trust the
    heuristic" unchanged in shape. A point-mass distribution (entropy
    exactly 0.0) always lands in the top bucket, matching every ground-
    truth caller's default. `HybridCopBrain`'s own "top bucket" check
    compares against `len(ENTROPY_THRESHOLDS)`, not a literal."""
    bucket = len(ENTROPY_THRESHOLDS)
    for threshold in ENTROPY_THRESHOLDS:
        if entropy < threshold:
            return bucket
        bucket -= 1
    return bucket
