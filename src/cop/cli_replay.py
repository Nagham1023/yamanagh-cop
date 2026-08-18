"""`uv run python -m cop replay --log <path>`'s real logic (rule 20
**[FATAL]**: "Build a viewer application" — singular, so both protocol
dialects share this one entry point rather than two competing tools).
Headless-first, deliberately: a real grader's own actual situation is
"just this log file, no live process, maybe no display" — a printed
verdict alone already gives everything a correct/incorrect answer needs.
`--gui` additionally opens a real window for either protocol's log shape —
std_v1 (a different commit-reveal scheme, `std_v1/crypto.py`) drives the
same `ReplayViewerWindow` through `std_v1/replay_viewer.py`'s own
`StdV1ReplayViewer`, which mirrors the native `ReplayViewer`'s navigation
surface. The format is sniffed from the file itself
(`replay_log.is_std_v1_log`), not a flag, so `--log <path>` always just
works.
"""

from __future__ import annotations

import sys

from .observability.replay_viewer import ReplayViewer, ReplayViewerWindow, nonces_from_log
from .std_v1.replay_log import is_std_v1_log
from .std_v1.replay_viewer import StdV1ReplayViewer


def _run_std_v1_replay(log_path: str, *, gui: bool = False) -> int:
    """std_v1's own branch of `run_replay` — separate from the native
    protocol's because its commit-reveal scheme is different
    (`std_v1/sealing.py`), but returns the same exit-code contract and,
    since `StdV1ReplayViewer` mirrors `ReplayViewer`'s interface, drives
    the identical `ReplayViewerWindow` under `--gui`."""
    viewer = StdV1ReplayViewer(log_path)
    print(f"Overall: {viewer.overall_status}")
    for step in viewer.steps:
        print(f"  step {step.step}: {'ok' if step.verified else 'TAMPERED'}")

    if gui:
        window = ReplayViewerWindow(viewer)
        window.root.mainloop()

    return 0 if viewer.passed else 1


def run_replay(log_path: str, *, gui: bool = False) -> int:
    """Prints a step-by-step verdict; returns a process exit code (`0` on
    `"Verified OK"`, `1` otherwise) — rule 20's own "no appeal" framing
    means an ambiguous exit code here would defeat the tool's purpose."""
    if is_std_v1_log(log_path):
        return _run_std_v1_replay(log_path, gui=gui)

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

    return 0 if viewer.passed else 1
