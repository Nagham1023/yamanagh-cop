"""`uv run python -m cop replay --log <path>`'s real logic (rule 20
**[FATAL]**). Headless-first, deliberately: a real grader's own actual
situation is "just this log file, no live process, maybe no display" —
`ReplayViewer` alone (no Tkinter import needed) already gives everything a
correct/incorrect verdict needs. `--gui` additionally opens the real
`ReplayViewerWindow` a human can look at, after the same verdict is
already printed — never the only way to get an answer.
"""

from __future__ import annotations

import sys

from .observability.replay_viewer import ReplayViewer, ReplayViewerWindow, nonces_from_log


def run_replay(log_path: str, *, gui: bool = False) -> int:
    """Prints a step-by-step verdict; returns a process exit code (`0` on
    `"Verified OK"`, `1` otherwise) — rule 20's own "no appeal" framing
    means an ambiguous exit code here would defeat the tool's purpose."""
    try:
        nonces = nonces_from_log(log_path)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    viewer = ReplayViewer(log_path, nonces)
    print(f"Overall: {viewer.overall_status}")
    for step in viewer.steps:
        status = "ok" if step.verified else "TAMPERED"
        print(f"  step {step.step}: {status}")

    if gui:
        window = ReplayViewerWindow(viewer)
        window.root.mainloop()

    return 0 if viewer.audit_result.passed else 1
