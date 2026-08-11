"""Structural check for the training/ <-> src/cop/ boundary (PRD 11).

`training/` may import from `src/cop/` (its own docstring, and PRD 11's PRD
file, both document this as one-directional) — but nothing under `src/cop/`
may ever import `training/`. Turns that boundary from a documented
convention into a regression-tested fact, the same pattern
`tests/unit/test_prd4_seam.py` already uses for its own seam.
"""

from __future__ import annotations

import re
from pathlib import Path

_IMPORT_PATTERN = re.compile(r"^\s*(from\s+training\b|import\s+training\b)", re.MULTILINE)


def test_nothing_under_src_cop_imports_training():
    repo_root = Path(__file__).resolve().parents[2]
    src_cop = repo_root / "src" / "cop"
    offenders = [
        str(path.relative_to(repo_root))
        for path in src_cop.rglob("*.py")
        if _IMPORT_PATTERN.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"src/cop/ files importing training/: {offenders}"


def test_the_check_itself_actually_catches_a_violation(tmp_path):
    """Verified this test guards the thing, not just that it usually
    passes — same discipline PRD 3's cycle-detection retrospective used."""
    offending_file = tmp_path / "would_be_violation.py"
    offending_file.write_text("from training.q_table import QTable\n", encoding="utf-8")
    assert _IMPORT_PATTERN.search(offending_file.read_text(encoding="utf-8")) is not None
