"""Structured per-run artifact I/O for the ML pipeline (PRD 13).

Every stage writes exactly one `<stage>_metrics.json` under
`training/runs/<run_id>/` — mirrors how `check_config.py` (deterministic
Python) already feeds `rule-auditor` (Claude judgment) today: this module
computes and records everything checkable; the new agents interpret it,
never re-derive it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RUNS_ROOT = Path("training/runs")


def run_dir(run_id: str) -> Path:
    """Ensures the directory exists — every caller of this (directly or via
    `checkpoint_path`/`quantized_checkpoint_path`/`write_stage_metrics`)
    intends to write into it; a stage that runs before any other for a
    given `run_id` must not fail just because the directory doesn't exist yet."""
    path = RUNS_ROOT / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def checkpoint_path(run_id: str) -> Path:
    return run_dir(run_id) / "checkpoint.json"


def quantized_checkpoint_path(run_id: str) -> Path:
    return run_dir(run_id) / "checkpoint_quantized.json"


def write_stage_metrics(run_id: str, stage: str, payload: dict[str, Any]) -> Path:
    path = run_dir(run_id) / f"{stage}_metrics.json"
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str), encoding="utf-8"
    )
    return path


def read_stage_metrics(run_id: str, stage: str) -> dict[str, Any]:
    path = run_dir(run_id) / f"{stage}_metrics.json"
    return json.loads(path.read_text(encoding="utf-8"))


def stage_metrics_exist(run_id: str, stage: str) -> bool:
    return (run_dir(run_id) / f"{stage}_metrics.json").exists()
