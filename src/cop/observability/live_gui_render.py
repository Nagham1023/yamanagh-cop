"""Pure, non-Tkinter Live GUI rendering logic (ch. 7.3, rules 8/9
**[FATAL]**) — split out of `live_gui.py` once that file grew past the
150-line house cap adding barrier/star rendering.

`render_state` is the actual rule 8/9 enforcement point (Design Question
2, `PRD-7-reporting-shell.md`): a pure function whose own parameter list
is `(own_pos, belief_probabilities, turn_state, barrier_positions,
scent_probabilities, hint_text)` and nothing else — no parameter admits a
true opponent `Position` or a full `GameState`/`Board`. Every one of these
is local-truth-safe: this cop's own position/placed barriers/sensed scent,
and a hint sent *to* this cop — the Local Truth principle (ch. 7.2) names
exactly these as the things an agent's own interface may show. Kept
deliberately separate from `LiveGuiWindow`'s own Tkinter widget code so
the boundary itself is testable by introspection alone, without needing a
real display.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.board import Position

_TURN_BANNER = {
    "WAITING_FOR_OPPONENT": ("...", "gray"),
    "COMPUTING_MOVE": ("YOUR TURN", "green"),
    "COMMITTING": ("LOCKED", "gray"),
    "AWAITING_REVEAL": ("LOCKED", "gray"),
    "VERIFYING": ("LOCKED", "gray"),
    "NEGOTIATING": ("STEP 0", "gray"),
}

_BARRIER_COLOR = "#1a1a1a"  # solid, near-black -- visually wins over any heatmap color


def _intensity(value: float, max_value: float) -> float:
    """The clamped-both-ends 0..1 ratio every heatmap color function
    builds on. `value` can be a tiny negative float (Bayesian floating-
    point rounding in `BeliefMap` — a "should be zero" cell landing at
    e.g. `-1e-18`) — a real bug found by running `scripts/watch_prd7_live_gui.py`
    live, not by a unit test: an upper-bound-only clamp let a negative
    `value`/`max_value` ratio through, and Tkinter rejected the resulting
    out-of-range color string outright. Clamped on both ends here, so
    every color function built on this is safe by construction, not by
    each one separately remembering to clamp."""
    return 0.0 if max_value <= 0 else max(0.0, min(1.0, value / max_value))


def _probability_to_color(value: float, max_value: float) -> str:
    """Deeper red for higher probability (ch. 7.3.1) — `max_value` is this
    render's own peak, not a fixed constant, so the map stays visually
    readable regardless of how concentrated or diffuse belief currently is."""
    green_blue = max(0, min(255, round(255 * (1 - _intensity(value, max_value)))))
    return f"#ff{green_blue:02x}{green_blue:02x}"


def _scent_to_color(value: float, max_value: float) -> str:
    """Deeper blue for higher currently-sensed scent — a deliberately
    different hue from belief's red, so the two heatmaps read as two
    distinct signals at a glance, not two shades of the same thing."""
    red_green = max(0, min(255, round(255 * (1 - _intensity(value, max_value)))))
    return f"#{red_green:02x}{red_green:02x}ff"


@dataclass(frozen=True)
class RenderedState:
    own_pos: Position
    grid_colors: dict[Position, str]
    banner_text: str
    banner_color: str
    most_likely_pos: Position | None = None
    barrier_positions: frozenset[Position] = field(default_factory=frozenset)
    scent_grid_colors: dict[Position, str] = field(default_factory=dict)
    hint_text: str | None = None


def render_state(
    own_pos: Position,
    belief_probabilities: dict[Position, float],
    turn_state: str,
    barrier_positions: frozenset[Position] = frozenset(),
    scent_probabilities: dict[Position, float] | None = None,
    hint_text: str | None = None,
) -> RenderedState:
    """The whole local-truth boundary lives in this one function's own
    signature — it is *impossible* to pass a true opponent position or an
    objective board through it, because no parameter admits one.

    `most_likely_pos` uses the same argmax convention
    `BeliefMap.most_likely_cell()` already does: `max()` over the dict,
    first-in-iteration-order tie-break — deterministic given `BeliefMap`'s
    own fixed cell-construction order, not re-derived or re-litigated
    here. `None` when `belief_probabilities` is empty (nothing to peak at).

    Barrier cells win over whatever heatmap color their own probability
    would otherwise produce — a barrier's real belief is already ~0 (per
    `BeliefMap.zero_out_barriers`), but this makes "blocked" visually
    explicit instead of indistinguishable from "just unlikely".

    `scent_probabilities` is a genuinely separate signal from belief (the
    cop's own currently-sensed `ScentField`, not the fused posterior) —
    `None`/absent treated as `{}`, an empty scent grid, not a crash.
    `hint_text` is this cop's own most recently *received* hint, shown
    verbatim — `None` when nothing has been received yet."""
    max_value = max(belief_probabilities.values(), default=0.0)
    grid_colors = {
        pos: _probability_to_color(value, max_value) for pos, value in belief_probabilities.items()
    }
    for pos in barrier_positions:
        grid_colors[pos] = _BARRIER_COLOR
    most_likely_pos = (
        max(belief_probabilities, key=belief_probabilities.get) if belief_probabilities else None
    )
    banner_text, banner_color = _TURN_BANNER.get(turn_state, ("?", "gray"))
    scent_probabilities = scent_probabilities or {}
    scent_max = max(scent_probabilities.values(), default=0.0)
    scent_grid_colors = {
        pos: _scent_to_color(value, scent_max) for pos, value in scent_probabilities.items()
    }
    return RenderedState(
        own_pos=own_pos,
        grid_colors=grid_colors,
        banner_text=banner_text,
        banner_color=banner_color,
        most_likely_pos=most_likely_pos,
        barrier_positions=frozenset(barrier_positions),
        scent_grid_colors=scent_grid_colors,
        hint_text=hint_text,
    )
