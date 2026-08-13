"""The Live GUI (ch. 7.3, rules 8/9 **[FATAL]**): local-truth-only — this
agent's own belief-map heatmap (deeper red = higher believed opponent
probability) side by side with its own currently-sensed scent heatmap
(deeper blue), a turn-state banner, this cop's own position, its own
placed barriers, a star over the currently most-likely believed opponent
cell, and the text of the last hint it received. Tkinter, stdlib, no new
dependency (`PRD-7-reporting-shell.md`'s Design Question 1).

Pure rendering logic (`render_state`/`RenderedState`, the actual rule 8/9
enforcement point) lives in `live_gui_render.py`; the background-thread
poll-loop session wrapper lives in `live_gui_session.py` — both split out
once this file grew past the 150-line house cap, the second time for a
class-responsibility split (single window vs. the session that drives it)
rather than a logic-vs-widget one.
"""

from __future__ import annotations

import tkinter as tk

from ..domain.board import Position
from .live_gui_render import RenderedState, render_state

__all__ = ["LiveGuiWindow", "RenderedState", "render_state"]


class LiveGuiWindow:
    """The actual Tkinter widget tree — thin: builds a canvas cell per
    believed-position/sensed-scent color and a banner/hint label, all
    sourced from `render_state`'s own output, never from anything else."""

    def __init__(self, board_size: int, cell_px: int = 40) -> None:
        self.root = tk.Tk()
        self.root.title("Cop Live GUI (Local Truth)")
        self._board_size = board_size
        self._cell_px = cell_px
        grids = tk.Frame(self.root)
        grids.pack()
        belief_col = tk.Frame(grids)
        belief_col.pack(side=tk.LEFT)
        tk.Label(belief_col, text="Belief").pack()
        self.canvas = tk.Canvas(belief_col, width=board_size * cell_px, height=board_size * cell_px, bg="white")
        self.canvas.pack()
        scent_col = tk.Frame(grids)
        scent_col.pack(side=tk.LEFT)
        tk.Label(scent_col, text="Scent Sensed").pack()
        self.scent_canvas = tk.Canvas(scent_col, width=board_size * cell_px, height=board_size * cell_px, bg="white")
        self.scent_canvas.pack()
        self.banner = tk.Label(self.root, text="...", font=("Helvetica", 16, "bold"), fg="gray")
        self.banner.pack()
        self.hint_label = tk.Label(self.root, text="(no hint received yet)", font=("Helvetica", 11))
        self.hint_label.pack()
        empty = {Position(c, r): "#ffffff" for c in range(board_size) for r in range(board_size)}
        self._paint_grid(self.canvas, empty)
        self._paint_grid(self.scent_canvas, empty)
        self.root.update_idletasks()
        self.root.update()

    def _paint_grid(self, canvas: tk.Canvas, grid_colors: dict[Position, str]) -> None:
        canvas.delete("all")
        for col in range(self._board_size):
            for row in range(self._board_size):
                pos = Position(col, row)
                color = grid_colors.get(pos, "#ffffff")
                x0, y0 = col * self._cell_px, row * self._cell_px
                canvas.create_rectangle(
                    x0, y0, x0 + self._cell_px, y0 + self._cell_px, fill=color, outline="black"
                )

    def update(self, rendered: RenderedState) -> None:
        self._paint_grid(self.canvas, rendered.grid_colors)
        self._paint_grid(self.scent_canvas, rendered.scent_grid_colors)
        px = self._cell_px
        if rendered.most_likely_pos is not None:
            star_x = rendered.most_likely_pos.col * px + px / 2
            star_y = rendered.most_likely_pos.row * px + px / 2
            self.canvas.create_text(
                star_x, star_y, text="★", fill="gold", font=("Helvetica", int(px * 0.6), "bold"),
                tags=("star",),
            )
        own_x0, own_y0 = rendered.own_pos.col * px, rendered.own_pos.row * px
        self.canvas.create_oval(
            own_x0 + 5, own_y0 + 5, own_x0 + px - 5, own_y0 + px - 5, fill="blue", tags=("own_marker",)
        )
        self.canvas.create_text(
            own_x0 + px / 2, own_y0 + px / 2, text="C", fill="white", font=("Helvetica", int(px * 0.4), "bold"),
            tags=("own_label",),
        )
        self.banner.config(text=rendered.banner_text, fg=rendered.banner_color)
        self.hint_label.config(text=rendered.hint_text or "(no hint received yet)")
        # `update()` (not only update_idletasks) is required on Windows or the
        # window stays blank / never maps its canvas contents.
        self.root.update_idletasks()
        self.root.update()

    def run(self) -> None:
        self.root.mainloop()

    def close(self) -> None:
        try:
            self.root.destroy()
        except tk.TclError:
            pass
