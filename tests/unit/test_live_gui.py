"""Rules 8/9 **[FATAL]**: the Live GUI must never render the opponent's
true position or the full objective board. The real test discipline
(`PRD-7-reporting-shell.md`'s Design Question 2, `PLAN.md`'s own "Also
verify" line): inspect what data reaches the render call, not a screenshot.
"""

from __future__ import annotations

import inspect
import tkinter

import pytest

from cop.domain.board import Position
from cop.observability.live_gui import LiveGuiWindow, RenderedState, render_state


def _display_available() -> bool:
    try:
        root = tkinter.Tk()
        root.destroy()
        return True
    except tkinter.TclError:
        return False


_HAS_DISPLAY = _display_available()


def test_render_state_signature_admits_no_true_opponent_position_or_board():
    """The actual rule 8/9 enforcement: `render_state`'s own parameter list
    is exhaustively `(own_pos, belief_probabilities, turn_state)` — nothing
    shaped like a true opponent `Position`, `GameState`, or `Board` can be
    passed through it, because no such parameter exists at all."""
    params = list(inspect.signature(render_state).parameters)
    assert params == ["own_pos", "belief_probabilities", "turn_state"]

    for name, param in inspect.signature(render_state).parameters.items():
        annotation = str(param.annotation)
        assert "GameState" not in annotation
        assert "Board" not in annotation or name != "own_pos"


def test_render_state_never_touches_a_true_position_value_at_runtime():
    # Even a caller trying to smuggle a "true" position in has nowhere to
    # put it — confirm the returned RenderedState only ever carries back
    # exactly what was given (this agent's own belief), nothing derived
    # from a second, hidden ground-truth source.
    own_pos = Position(2, 2)
    belief = {Position(5, 5): 0.9, Position(1, 1): 0.1}

    rendered = render_state(own_pos, belief, "COMPUTING_MOVE")

    assert rendered.own_pos == own_pos
    assert set(rendered.grid_colors) == set(belief)


def test_a_tiny_negative_probability_still_produces_a_valid_color():
    # Found by running scripts/watch_prd7_live_gui.py live, not by a unit
    # test: a "should be zero" belief cell can land at a tiny negative
    # float (Bayesian floating-point rounding) — _probability_to_color must
    # clamp it, not hand Tkinter an out-of-range color string.
    belief = {Position(0, 0): -1e-18, Position(1, 1): 0.5}
    rendered = render_state(Position(0, 0), belief, "COMPUTING_MOVE")

    for color in rendered.grid_colors.values():
        assert len(color) == 7 and color.startswith("#")
        int(color[1:], 16)  # raises ValueError if not valid hex


def test_an_entirely_zero_belief_map_produces_a_valid_color_not_a_division_by_zero():
    # max_value == 0 (e.g. a belief dict wiped to all-zero) — the max_value
    # <= 0 branch must short-circuit to intensity=0.0 rather than dividing.
    belief = {Position(0, 0): 0.0, Position(1, 1): 0.0}
    rendered = render_state(Position(0, 0), belief, "COMPUTING_MOVE")

    for color in rendered.grid_colors.values():
        assert color == "#ffffff"


def test_the_highest_probability_cell_is_visually_distinguishable():
    belief = {Position(0, 0): 0.05, Position(3, 3): 0.9, Position(6, 6): 0.05}
    rendered = render_state(Position(0, 0), belief, "COMPUTING_MOVE")

    uniform_baseline_color = rendered.grid_colors[Position(0, 0)]
    highest_color = rendered.grid_colors[Position(3, 3)]
    assert highest_color != uniform_baseline_color
    # Deeper red = smaller green/blue channel value, per the module's own
    # "deeper red = higher probability" convention (ch. 7.3.1).
    assert highest_color < uniform_baseline_color


def test_turn_state_maps_to_the_right_banner():
    your_turn = render_state(Position(0, 0), {}, "COMPUTING_MOVE")
    assert your_turn.banner_text == "YOUR TURN"
    assert your_turn.banner_color == "green"

    locked = render_state(Position(0, 0), {}, "COMMITTING")
    assert locked.banner_text == "LOCKED"
    assert locked.banner_color == "gray"


def test_render_state_returns_a_rendered_state_dataclass():
    rendered = render_state(Position(0, 0), {}, "WAITING_FOR_OPPONENT")
    assert isinstance(rendered, RenderedState)


@pytest.mark.skipif(not _HAS_DISPLAY, reason="no display available for a real Tk window")
def test_live_gui_window_actually_renders_without_crashing():
    window = LiveGuiWindow(board_size=7)
    try:
        rendered = render_state(Position(0, 0), {Position(3, 3): 0.9}, "COMPUTING_MOVE")
        window.update(rendered)
        assert window.banner.cget("text") == "YOUR TURN"
    finally:
        window.close()
