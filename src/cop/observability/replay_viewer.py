"""The Replay Viewer (ch. 7.4, rule 20 **[FATAL]**): reads a recorded
`log_<game_id>_g<NN>.json`, steps through it, stamps `Verified OK`/`TAMPERED`.

Wraps `integrity/audit.py::run_mutual_audit` (`PRD-7-reporting-shell.md`'s
Design Question 4) — not ch. 7.5's illustrative 2-field sketch — so the
Replay Viewer can never silently diverge from the real cryptographic
machinery every other layer already uses. Runs the full audit **once**, on
load; per-step navigation only ever reads that one already-computed
result, never re-verifies (ch. 7.4's own wording: the match is disqualified
on the *first* mismatch, no appeal — there is no "partially verified" state
to recompute into).
"""

from __future__ import annotations

import json
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path

from ..integrity.audit import AuditResult, run_mutual_audit


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


@dataclass(frozen=True)
class StepView:
    step: int
    event: dict
    verified: bool


class ReplayViewer:
    def __init__(self, log_path: str | Path, nonces: dict[int, str]) -> None:
        self.log_path = Path(log_path)
        self.audit_result: AuditResult = run_mutual_audit(self.log_path, nonces)
        self.steps: list[StepView] = self._load_steps()
        self._index = 0

    def _load_steps(self) -> list[StepView]:
        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        entries = [json.loads(line) for line in lines if line.strip()]
        committing_entries = [e for e in entries if e.get("event") == "committing"]
        mismatched_steps = {m["step"] for m in self.audit_result.mismatches if "step" in m}
        return [
            StepView(step=e["step"], event=e, verified=e["step"] not in mismatched_steps)
            for e in committing_entries
        ]

    @property
    def overall_status(self) -> str:
        return "Verified OK" if self.audit_result.passed else "TAMPERED"

    def current(self) -> StepView | None:
        return self.steps[self._index] if self.steps else None

    def step_forward(self) -> StepView | None:
        if self._index < len(self.steps) - 1:
            self._index += 1
        return self.current()

    def step_backward(self) -> StepView | None:
        if self._index > 0:
            self._index -= 1
        return self.current()


class ReplayViewerWindow:
    """Same toolkit as `live_gui.py` (Tkinter, stdlib) — step controls and
    an overall `Verified OK`/`TAMPERED` banner, sourced entirely from a
    `ReplayViewer`'s own already-computed result."""

    def __init__(self, viewer: ReplayViewer) -> None:
        self.viewer = viewer
        self.root = tk.Tk()
        self.root.title("Replay Viewer")
        color = "green" if viewer.audit_result.passed else "red"
        self.banner = tk.Label(
            self.root, text=viewer.overall_status, font=("Helvetica", 20, "bold"), fg=color
        )
        self.banner.pack()
        self.step_label = tk.Label(self.root, text="", font=("Helvetica", 12))
        self.step_label.pack()
        tk.Button(self.root, text="< Back", command=self._back).pack(side=tk.LEFT)
        tk.Button(self.root, text="Forward >", command=self._forward).pack(side=tk.RIGHT)
        self._refresh()

    def _refresh(self) -> None:
        step = self.viewer.current()
        if step is None:
            self.step_label.config(text="(no committed steps in this log)")
            return
        status = "ok" if step.verified else "TAMPERED"
        self.step_label.config(text=f"step {step.step}: {status}")

    def _forward(self) -> None:
        self.viewer.step_forward()
        self._refresh()

    def _back(self) -> None:
        self.viewer.step_backward()
        self._refresh()

    def close(self) -> None:
        self.root.destroy()
