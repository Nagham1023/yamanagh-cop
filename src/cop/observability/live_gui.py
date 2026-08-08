"""The Live GUI (ch. 7.3, rules 8/9 **[FATAL]**): local-truth-only — this
agent's own belief-map heatmap (deeper red = higher believed opponent
probability) and a turn-state banner. Tkinter, stdlib, no new dependency
(`PRD-7-reporting-shell.md`'s Design Question 1).

`render_state` is the actual rule 8/9 enforcement point (Design Question
2): a pure function whose own parameter list is `(own_pos, belief_probabilities,
turn_state)` and nothing else — no parameter admits a true opponent
`Position` or a full `GameState`/`Board`. Deliberately separated from
`LiveGuiWindow`'s own Tkinter widget code so the boundary itself is
testable by introspection alone, without needing a real display.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass

from ..domain.board import Position

_TURN_BANNER = {
    "WAITING_FOR_OPPONENT": ("...", "gray"),
    "COMPUTING_MOVE": ("YOUR TURN", "green"),
    "COMMITTING": ("LOCKED", "gray"),
    "AWAITING_REVEAL": ("LOCKED", "gray"),
    "VERIFYING": ("LOCKED", "gray"),
}


def _probability_to_color(value: float, max_value: float) -> str:
    """Deeper red for higher probability (ch. 7.3.1) — `max_value` is this
    render's own peak, not a fixed constant, so the map stays visually
    readable regardless of how concentrated or diffuse belief currently is.

    `value` can be a tiny negative float (Bayesian floating-point rounding
    in `BeliefMap` — a "should be zero" cell landing at e.g. `-1e-18`) — a
    real bug found by running `scripts/watch_prd7_live_gui.py` live, not by
    a unit test: `intensity` was only clamped on its upper bound, so a
    negative `value`/`max_value` ratio produced a `green_blue` far outside
    `0-255` and Tkinter rejected the resulting color string outright.
    Clamped on both ends now, defensively double-clamped after rounding
    too — never trust a single clamp for a value about to leave Python."""
    intensity = 0.0 if max_value <= 0 else max(0.0, min(1.0, value / max_value))
    green_blue = round(255 * (1 - intensity))
    green_blue = max(0, min(255, green_blue))
    return f"#ff{green_blue:02x}{green_blue:02x}"


@dataclass(frozen=True)
class RenderedState:
    own_pos: Position
    grid_colors: dict[Position, str]
    banner_text: str
    banner_color: str


def render_state(
    own_pos: Position, belief_probabilities: dict[Position, float], turn_state: str
) -> RenderedState:
    """The whole local-truth boundary lives in this one function's own
    signature — it is *impossible* to pass a true opponent position or an
    objective board through it, because no parameter admits one."""
    max_value = max(belief_probabilities.values(), default=0.0)
    grid_colors = {
        pos: _probability_to_color(value, max_value) for pos, value in belief_probabilities.items()
    }
    banner_text, banner_color = _TURN_BANNER.get(turn_state, ("?", "gray"))
    return RenderedState(
        own_pos=own_pos, grid_colors=grid_colors, banner_text=banner_text, banner_color=banner_color
    )


class LiveGuiWindow:
    """The actual Tkinter widget tree — thin: builds a canvas cell per
    believed-position color and a banner label, both sourced from
    `render_state`'s own output, never from anything else."""

    def __init__(self, board_size: int, cell_px: int = 40) -> None:
        self.root = tk.Tk()
        self.root.title("Cop Live GUI (Local Truth)")
        self.canvas = tk.Canvas(self.root, width=board_size * cell_px, height=board_size * cell_px)
        self.canvas.pack()
        self.banner = tk.Label(self.root, text="", font=("Helvetica", 16, "bold"))
        self.banner.pack()
        self._cell_px = cell_px

    def update(self, rendered: RenderedState) -> None:
        self.canvas.delete("all")
        for pos, color in rendered.grid_colors.items():
            x0, y0 = pos.col * self._cell_px, pos.row * self._cell_px
            self.canvas.create_rectangle(
                x0, y0, x0 + self._cell_px, y0 + self._cell_px, fill=color, outline="black"
            )
        px = self._cell_px
        own_x0, own_y0 = rendered.own_pos.col * px, rendered.own_pos.row * px
        self.canvas.create_oval(own_x0 + 5, own_y0 + 5, own_x0 + px - 5, own_y0 + px - 5, fill="blue")
        self.banner.config(text=rendered.banner_text, fg=rendered.banner_color)
        self.root.update_idletasks()

    def close(self) -> None:
        self.root.destroy()
