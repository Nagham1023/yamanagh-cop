"""std_v1's own navigable replay viewer (rule 20 **[FATAL]**: "Build a
viewer application" — singular — so `--gui` is not a native-protocol-only
feature). Mirrors `observability/replay_viewer.py::ReplayViewer`'s public
surface (`overall_status`, `passed`, `halted`, `current()`,
`step_forward()`, `step_backward()`) so the one `ReplayViewerWindow` can
drive either protocol's viewer via duck typing, without a second GUI class
to keep in sync. Built on top of `verify_sub_game_log`'s already-computed
per-step result rather than re-deriving the hash check itself.
"""

from __future__ import annotations

from pathlib import Path

from ..observability.replay_viewer import StepView
from .replay_log import verify_sub_game_log

__all__ = ["StdV1ReplayViewer"]


class StdV1ReplayViewer:
    """Navigable, pre-computed verdict over one std_v1 sub-game log — the
    std_v1 counterpart to `ReplayViewer`, kept as a separate class (not a
    subclass) because the two protocols' underlying verification calls
    (`verify_sub_game_log` vs. `run_mutual_audit`) take different inputs
    and can't share a constructor."""

    def __init__(self, log_path: str | Path) -> None:
        self.log_path = Path(log_path)
        result = verify_sub_game_log(self.log_path)
        self.passed: bool = result["passed"]
        self.steps: list[StepView] = [
            StepView(step=step["step"], event={}, verified=step["verified"])
            for step in result["steps"]
        ]
        self._index = 0
        # Same "computed once, never recomputed" halt point as the native
        # viewer (docstring in observability/replay_viewer.py) — the first
        # tampered step is where navigation must stop, permanently.
        self._first_tampered_index: int | None = next(
            (i for i, step in enumerate(self.steps) if not step.verified), None
        )

    @property
    def overall_status(self) -> str:
        return "Verified OK" if self.passed else "TAMPERED"

    @property
    def halted(self) -> bool:
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
