"""`LiveGuiSession` — split out of `live_gui.py` once that file grew past
the 150-line house cap adding the scent canvas/hint label; a class-
responsibility split (the single window vs. the session that drives it),
not a logic-vs-widget one this time.

Mirrors the Thief peer's LiveSession pattern: the match runs on a
background thread while Tk `mainloop` owns the main thread and polls
orchestrator state via `.after()`. Creating a `Tk()` under `asyncio.run`
and only calling `update_idletasks()` leaves a blank window on Windows —
that was the live `--gui` failure mode.
"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from typing import Any

from .live_gui import LiveGuiWindow
from .live_gui_render import render_state


class LiveGuiSession:
    """Match on a background thread; Tk mainloop + `.after` poll on the
    thread that constructed this session (must be the process main thread
    on Windows)."""

    def __init__(self, orchestrator: Any, board_size: int, poll_interval_ms: int = 200) -> None:
        self._orchestrator = orchestrator
        self._window = LiveGuiWindow(board_size=board_size)
        self._poll_interval_ms = poll_interval_ms
        self._match_done = threading.Event()
        self._error: BaseException | None = None
        self.result: Any = None

    def run(self, match_fn: Callable[[], Any]) -> Any:
        thread = threading.Thread(target=self._run_match, args=(match_fn,), daemon=True)
        thread.start()
        self._schedule_poll()
        self._window.run()
        thread.join(timeout=5.0)
        if self._error is not None:
            raise self._error
        return self.result

    def _run_match(self, match_fn: Callable[[], Any]) -> None:
        try:
            self.result = match_fn()
        except BaseException as exc:  # noqa: BLE001 — re-raised on the GUI thread
            self._error = exc
        finally:
            self._match_done.set()

    def _schedule_poll(self) -> None:
        try:
            orch = self._orchestrator
            rendered = render_state(
                orch.game_state.own_pos,
                orch.belief_map._probabilities,
                str(orch.state_machine.state),
                frozenset(orch.game_state.barriers.placed),
                orch.scent_field.full_field(),
                getattr(orch, "_last_hint_received", None),
            )
            self._window.update(rendered)
            if not self._match_done.is_set():
                self._window.root.after(self._poll_interval_ms, self._schedule_poll)
            else:
                self._window.root.after(800, self._window.root.quit)
        except tk.TclError:
            pass
