"""The Replay Viewer (ch. 7.4, rule 20 **[FATAL]**): reads a recorded
`log_<game_id>_g<NN>.json`, steps through it, stamps `Verified OK`/`TAMPERED`.

Wraps `integrity/audit.py::run_mutual_audit` (`PRD-7-reporting-shell.md`'s
Design Question 4) — not ch. 7.5's illustrative 2-field sketch — so the
Replay Viewer can never silently diverge from the real cryptographic
machinery every other layer already uses. Runs the full audit **once**, on
load; per-step navigation only ever reads that one already-computed
result, never re-verifies (ch. 7.4's own wording: the match is disqualified
on the *first* mismatch, no appeal — there is no "partially verified" state
to recompute into). A separate product-style spec described a per-step
`verify_step`-shaped UI that recalculates hashes on each click — this is a
genuine, documented contradiction, resolved in `README.md` §5 (bulk audit
kept as-is; the real, actionable gap that surfaced alongside it — nothing
stopped navigation past a confirmed tamper point — is fixed below instead).

**Halt on tamper**: `step_forward()` refuses to advance past the first
tampered step once one exists — you can review everything up to and
including it, but never step beyond it. `step_backward()` is unrestricted;
reviewing what led to disqualification stays fully available.
"""

from __future__ import annotations

import json
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path

from ..integrity.audit import AuditResult, run_mutual_audit
from .replay_nonces import nonces_from_log

__all__ = ["ReplayViewer", "ReplayViewerWindow", "StepView", "nonces_from_log"]


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
        # Computed once here, never recomputed — the index (not step number)
        # of the first unverified StepView, or None on a clean log. `next()`
        # over `enumerate` rather than a second pass over the raw mismatch
        # set, so this is defined purely in terms of self.steps' own order.
        self._first_tampered_index: int | None = next(
            (i for i, step in enumerate(self.steps) if not step.verified), None
        )

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

    @property
    def halted(self) -> bool:
        """True exactly when navigation is currently sitting at the first
        tampered step — the point past which `step_forward()` refuses to
        advance. `False` on a clean log (`_first_tampered_index is None`)
        and `False` everywhere before that step too."""
        return self._first_tampered_index is not None and self._index == self._first_tampered_index

    def current(self) -> StepView | None:
        return self.steps[self._index] if self.steps else None

    def step_forward(self) -> StepView | None:
        at_limit = self._first_tampered_index is not None and self._index >= self._first_tampered_index
        if self._index < len(self.steps) - 1 and not at_limit:
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
        self.back_button = tk.Button(self.root, text="< Back", command=self._back)
        self.back_button.pack(side=tk.LEFT)
        self.forward_button = tk.Button(self.root, text="Forward >", command=self._forward)
        self.forward_button.pack(side=tk.RIGHT)
        self._refresh()

    def _refresh(self) -> None:
        # Named, stateful buttons (not the original anonymous pack()-only
        # calls) so this can actually disable Forward once halted, rather
        # than just labeling a step "TAMPERED" while still letting
        # navigation walk straight past the disqualification point.
        self.forward_button.config(state=tk.DISABLED if self.viewer.halted else tk.NORMAL)
        step = self.viewer.current()
        if step is None:
            self.step_label.config(text="(no committed steps in this log)")
            return
        status = "ok" if step.verified else "TAMPERED"
        label = f"step {step.step}: {status}"
        if self.viewer.halted:
            label += " — further steps blocked (disqualified)"
        self.step_label.config(text=label)

    def _forward(self) -> None:
        self.viewer.step_forward()
        self._refresh()

    def _back(self) -> None:
        self.viewer.step_backward()
        self._refresh()

    def close(self) -> None:
        self.root.destroy()
