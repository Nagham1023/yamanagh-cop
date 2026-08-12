"""The ML pipeline's stage logic and artifact I/O (PRD 13).

Lives inside `training/` (already sandbox-only, one-directional dependency
on `src/cop/`) rather than under `scripts/ml/` — `scripts/` has no existing
precedent of being imported as a package (every `watch_prd*.py` file is a
standalone, human-watched demo, never unit-tested directly). This layer
genuinely needs unit tests (the refinement loop's cap/criterion/budget,
each stage's artifact shape), so the substantial logic lives here, properly
importable, and `scripts/ml/orchestrate_pipeline.py` stays a thin CLI
wrapper — the same split this repo already uses for `__main__.py` vs.
`cli_peer.py`.
"""

from __future__ import annotations
