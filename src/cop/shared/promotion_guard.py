"""Hard runtime guard for counted games against a promoted RL brain (PRD 13).

Auto-replace deployment (this repo's chosen posture) means there is no
"human edits `config/game.toml`" gesture left to attach a promotion
checkpoint to — `RLCopBrain` becomes the default the instant a promotion
commit lands. This guard is the safety net that replaces that manual
gesture: a *counted* game refuses to start unless
`training/promoted/promotion_report.json` exists and its recorded
checkpoint hash matches the checkpoint file actually on disk. Uncounted
(warm-up) games are never affected, and neither is any brain other than
`RLCopBrain` — this is not a generic gate for arbitrary custom brains.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..reasoning.brain_base import BrainBase
from ..reasoning.rl_cop_brain import DEFAULT_CHECKPOINT_PATH, RLCopBrain

PROMOTION_REPORT_PATH = Path("training/promoted/promotion_report.json")


class StalePromotionError(RuntimeError):
    """A counted game would run against `RLCopBrain` with no current,
    matching promotion report — never raised for any other brain class."""


def require_fresh_promotion_report_for_counted_game(brain: BrainBase, *, counted: bool) -> None:
    """No-op for every case except a counted game against `RLCopBrain` —
    see the module docstring for why that's the one case needing a guard."""
    if not counted or not isinstance(brain, RLCopBrain):
        return

    if not PROMOTION_REPORT_PATH.exists():
        raise StalePromotionError(
            f"counted game refused: {PROMOTION_REPORT_PATH} does not exist — "
            "RLCopBrain has never been promoted (see the ml-promotion-gate agent)."
        )

    checkpoint_path = Path(DEFAULT_CHECKPOINT_PATH)
    if not checkpoint_path.exists():
        raise StalePromotionError(
            f"counted game refused: promoted checkpoint {checkpoint_path} is missing."
        )

    report = json.loads(PROMOTION_REPORT_PATH.read_text(encoding="utf-8"))
    actual_hash = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
    if report.get("checkpoint_sha256") != actual_hash:
        raise StalePromotionError(
            f"counted game refused: {PROMOTION_REPORT_PATH}'s recorded checkpoint hash "
            f"does not match {checkpoint_path} on disk — retrain/re-promote, or the "
            "report is stale."
        )
