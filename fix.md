# fix.md — make `--gui` work for std_v1 replay logs too

## Problem

`cli_replay.py::_run_std_v1_replay` silently ignores the `gui` flag — a
std_v1 log never opens the Tkinter replay window, even though `--log
<path>` already auto-sniffs protocol via `is_std_v1_log` and both dialects
share the same `run_replay` entry point. Rule 20 **[FATAL]** calls for
*one* viewer application covering both dialects, not a native-only
feature with std_v1 as a print-only second-class citizen.

## Root cause

`observability/replay_viewer.py::ReplayViewer` (native) and
`std_v1/replay_log.py::verify_sub_game_log` (std_v1) never shared an
interface. Only the native side has a `ReplayViewer`-shaped object to
hand `ReplayViewerWindow`.

## Plan

- [ ] 1. `src/cop/std_v1/replay_viewer.py` (new file): `StdV1ReplayViewer`
      class exposing the same navigation surface as
      `observability/replay_viewer.py::ReplayViewer`
      (`overall_status`, `passed`, `halted`, `current()`, `step_forward()`,
      `step_backward()`), built from `verify_sub_game_log()`'s per-step
      result. Reuses `StepView` from `observability/replay_viewer.py`
      rather than a second copy of the same dataclass.
- [ ] 2. `src/cop/observability/replay_viewer.py`: add a `passed` property
      to `ReplayViewer` (`self.audit_result.passed`) and switch
      `ReplayViewerWindow.__init__`'s banner-color check from
      `viewer.audit_result.passed` to `viewer.passed`, so the window works
      for either viewer type via duck typing instead of assuming a
      native-only `audit_result` attribute. Keep `audit_result` itself
      untouched (existing tests read it directly).
- [ ] 3. `src/cop/cli_replay.py`: give `_run_std_v1_replay` a
      `gui: bool = False` parameter; when set, build a `StdV1ReplayViewer`
      and open a `ReplayViewerWindow` + `mainloop()`, mirroring the native
      branch exactly. Update `run_replay`'s dispatch call to pass
      `gui=gui` through.
- [ ] 4. Tests:
      - `tests/unit/test_std_v1_replay_viewer.py` (new): clean-log
        pass/halt behavior, and a **rejection** case (tampered record ->
        `halted` True, `step_forward()` refuses to advance past it) —
        mirrors the native `ReplayViewer` tests' shape. A
        display-gated `ReplayViewerWindow` construction test (banner
        color, forward-disable-on-tamper), skipped when no display,
        matching the existing `_HAS_DISPLAY` pattern in
        `test_replay_viewer.py`.
      - `tests/unit/test_cli_replay.py`: add a non-gui std_v1 dispatch
        test through `run_replay()` (currently missing entirely — only
        `verify_sub_game_log` is tested directly today).
- [ ] 5. `uv run pytest` full run, then `spec-guard` before calling this
      done, per CLAUDE.md's "run spec-guard before every commit."
