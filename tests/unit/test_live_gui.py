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
    is exhaustively `(own_pos, belief_probabilities, turn_state,
    barrier_positions, scent_probabilities, hint_text)` — nothing shaped
    like a true opponent `Position`, `GameState`, or `Board` can be passed
    through it, because no such parameter exists at all. Every one of
    these is local-truth-safe (ch. 7.2's own three named things an agent's
    interface may show, plus the cop's own barriers) — not a rule 8/9
    exception."""
    params = list(inspect.signature(render_state).parameters)
    assert params == [
        "own_pos", "belief_probabilities", "turn_state",
        "barrier_positions", "scent_probabilities", "hint_text",
    ]

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


def test_most_likely_pos_is_the_real_argmax():
    belief = {Position(0, 0): 0.05, Position(3, 3): 0.9, Position(6, 6): 0.05}
    rendered = render_state(Position(0, 0), belief, "COMPUTING_MOVE")
    assert rendered.most_likely_pos == Position(3, 3)


def test_most_likely_pos_is_none_for_an_empty_belief_map():
    rendered = render_state(Position(0, 0), {}, "COMPUTING_MOVE")
    assert rendered.most_likely_pos is None


def test_a_barrier_cell_renders_as_the_barrier_color_even_if_it_would_otherwise_be_the_hottest_cell():
    # Constructed so the barrier cell would trivially win an unfiltered
    # argmax/color comparison -- proves the barrier override is real, not
    # just coincidentally matching a low-probability cell.
    barrier_cell = Position(4, 4)
    belief = {barrier_cell: 0.99, Position(0, 0): 0.01}
    rendered = render_state(
        Position(0, 0), belief, "COMPUTING_MOVE", barrier_positions=frozenset({barrier_cell})
    )
    assert rendered.grid_colors[barrier_cell] == "#1a1a1a"


def test_barrier_positions_round_trips_the_input():
    barriers = frozenset({Position(2, 2), Position(3, 3)})
    rendered = render_state(Position(0, 0), {}, "COMPUTING_MOVE", barrier_positions=barriers)
    assert rendered.barrier_positions == barriers


def test_scent_grid_colors_deeper_blue_for_higher_sensed_scent():
    scent = {Position(0, 0): 0.05, Position(3, 3): 0.9, Position(6, 6): 0.05}
    rendered = render_state(Position(0, 0), {}, "COMPUTING_MOVE", scent_probabilities=scent)

    baseline_color = rendered.scent_grid_colors[Position(0, 0)]
    highest_color = rendered.scent_grid_colors[Position(3, 3)]
    assert highest_color != baseline_color
    # Deeper blue = smaller red/green channel value, same convention shape
    # _probability_to_color already uses for red, just a different hue.
    assert highest_color < baseline_color
    for color in rendered.scent_grid_colors.values():
        assert color.endswith("ff")  # blue channel pinned, never scaled down


def test_a_tiny_negative_scent_value_still_produces_a_valid_color():
    # Same real bug class _probability_to_color's own docstring documents,
    # exercised through the scent path too -- both color functions share
    # the same clamped _intensity() helper, but this proves it end to end.
    scent = {Position(0, 0): -1e-18, Position(1, 1): 0.5}
    rendered = render_state(Position(0, 0), {}, "COMPUTING_MOVE", scent_probabilities=scent)
    for color in rendered.scent_grid_colors.values():
        assert len(color) == 7 and color.startswith("#")
        int(color[1:], 16)


def test_scent_probabilities_defaults_to_an_empty_grid_not_a_crash():
    rendered = render_state(Position(0, 0), {}, "COMPUTING_MOVE")
    assert rendered.scent_grid_colors == {}


def test_a_cell_hot_in_both_belief_and_scent_gets_two_genuinely_different_colors():
    # Proves belief and scent are actually independent signals computed
    # separately -- not the same computation reused for both grids.
    hot_cell = Position(3, 3)
    rendered = render_state(
        Position(0, 0), {hot_cell: 0.9}, "COMPUTING_MOVE", scent_probabilities={hot_cell: 0.9}
    )
    assert rendered.grid_colors[hot_cell] != rendered.scent_grid_colors[hot_cell]
    assert rendered.grid_colors[hot_cell].startswith("#ff")  # belief: red-pinned
    assert rendered.scent_grid_colors[hot_cell].endswith("ff")  # scent: blue-pinned


def test_hint_text_round_trips_and_defaults_to_none():
    rendered = render_state(Position(0, 0), {}, "COMPUTING_MOVE", hint_text="quiet by the river")
    assert rendered.hint_text == "quiet by the river"

    default_rendered = render_state(Position(0, 0), {}, "COMPUTING_MOVE")
    assert default_rendered.hint_text is None


@pytest.mark.skipif(not _HAS_DISPLAY, reason="no display available for a real Tk window")
def test_live_gui_window_actually_renders_without_crashing():
    window = LiveGuiWindow(board_size=7)
    try:
        rendered = render_state(Position(0, 0), {Position(3, 3): 0.9}, "COMPUTING_MOVE")
        window.update(rendered)
        assert window.banner.cget("text") == "YOUR TURN"
        # Full board is always painted (missing belief cells stay white) —
        # never an empty canvas waiting on the first sparse update.
        assert window.canvas.find_all()
    finally:
        window.close()


@pytest.mark.skipif(not _HAS_DISPLAY, reason="no display available for a real Tk window")
def test_live_gui_window_draws_a_star_and_own_label_and_barrier_square():
    window = LiveGuiWindow(board_size=7)
    try:
        rendered = render_state(
            Position(0, 0),
            {Position(3, 3): 0.9},
            "COMPUTING_MOVE",
            barrier_positions=frozenset({Position(5, 5)}),
        )
        window.update(rendered)
        assert window.canvas.find_withtag("star")  # the most-likely-cell marker
        assert window.canvas.find_withtag("own_label")  # the 'C' text on the cop's own cell
        assert window.canvas.find_withtag("own_marker")  # the pre-existing blue circle, unchanged
        # The barrier cell's own rectangle actually got the barrier fill —
        # not just present, the right color.
        barrier_x = 5 * window._cell_px + 1
        barrier_y = 5 * window._cell_px + 1
        item = window.canvas.find_closest(barrier_x, barrier_y)
        assert window.canvas.itemcget(item, "fill") == "#1a1a1a"
    finally:
        window.close()


@pytest.mark.skipif(not _HAS_DISPLAY, reason="no display available for a real Tk window")
def test_live_gui_window_paints_a_full_grid_on_construction():
    window = LiveGuiWindow(board_size=3)
    try:
        # 3x3 cells drawn before any belief update — fixes the blank-window
        # Windows failure mode when --gui opened under asyncio with no paint.
        assert len(window.canvas.find_all()) == 9
        assert len(window.scent_canvas.find_all()) == 9  # the second grid too, from construction
    finally:
        window.close()


@pytest.mark.skipif(not _HAS_DISPLAY, reason="no display available for a real Tk window")
def test_live_gui_window_paints_the_scent_canvas_and_updates_the_hint_label():
    window = LiveGuiWindow(board_size=7)
    try:
        rendered = render_state(
            Position(0, 0),
            {Position(3, 3): 0.9},
            "COMPUTING_MOVE",
            scent_probabilities={Position(4, 4): 0.8},
            hint_text="quiet by the river",
        )
        window.update(rendered)
        assert len(window.scent_canvas.find_all()) == 49  # full 7x7 grid, not just the hot cell
        assert window.hint_label.cget("text") == "quiet by the river"
    finally:
        window.close()


@pytest.mark.skipif(not _HAS_DISPLAY, reason="no display available for a real Tk window")
def test_live_gui_window_hint_label_falls_back_to_the_placeholder_when_none():
    window = LiveGuiWindow(board_size=7)
    try:
        rendered = render_state(Position(0, 0), {}, "COMPUTING_MOVE")  # hint_text defaults to None
        window.update(rendered)
        assert window.hint_label.cget("text") == "(no hint received yet)"
    finally:
        window.close()


def test_live_gui_session_runs_match_fn_and_returns_its_result(monkeypatch):
    """No real Tk mainloop — prove the session wires match_fn + quit path."""
    from cop.observability import live_gui_session as live_gui_mod

    class _FakeWindow:
        def __init__(self, board_size: int):
            self.root = type("R", (), {})()
            self.root.after = lambda _ms, cb: cb() if False else None  # noqa: ARG005
            self.updates = []
            self.ran = False

        def update(self, rendered):
            self.updates.append(rendered)

        def run(self):
            self.ran = True

        def close(self):
            pass

    # Avoid spinning forever: first poll sees match already done and quits.
    class _QuitWindow(_FakeWindow):
        def __init__(self, board_size: int):
            super().__init__(board_size)
            self._session = None

        def run(self):
            self.ran = True
            # Simulate mainloop returning after match thread finished.
            while not self._session._match_done.wait(timeout=0.05):
                pass

    orch = type(
        "O",
        (),
        {
            "game_state": type(
                "G", (), {"own_pos": Position(1, 1), "barriers": type("BS", (), {"placed": set()})()}
            )(),
            "belief_map": type("B", (), {"_probabilities": {Position(1, 1): 1.0}})(),
            "state_machine": type("S", (), {"state": "COMPUTING_MOVE"})(),
        },
    )()

    window_holder = {}

    def _fake_window(board_size: int):
        w = _QuitWindow(board_size)
        window_holder["w"] = w
        return w

    monkeypatch.setattr(live_gui_mod, "LiveGuiWindow", _fake_window)

    session = live_gui_mod.LiveGuiSession(orch, board_size=7, poll_interval_ms=1)
    window_holder["w"]._session = session

    # Don't schedule real after-callbacks; inject a one-shot poll then stop.
    def _poll_once():
        rendered = live_gui_mod.render_state(
            orch.game_state.own_pos,
            orch.belief_map._probabilities,
            str(orch.state_machine.state),
            frozenset(orch.game_state.barriers.placed),
        )
        window_holder["w"].update(rendered)

    monkeypatch.setattr(session, "_schedule_poll", _poll_once)

    result = session.run(lambda: "ok-outcome")
    assert result == "ok-outcome"
    assert window_holder["w"].ran is True
    assert window_holder["w"].updates


def test_the_real_schedule_poll_reads_barriers_scent_and_hint_not_a_stub(monkeypatch):
    """Unlike the test above (which monkeypatches _schedule_poll away
    entirely), this exercises the REAL method body directly, proving the
    production code actually reads orch.game_state.barriers.placed,
    orch.scent_field.full_field(), and orch._last_hint_received and
    threads all three through to render_state -- not just that a
    hand-written stub could."""
    from cop.observability import live_gui_session as live_gui_mod

    class _FakeWindow:
        def __init__(self, board_size: int):
            self.root = type(
                "R", (), {"after": staticmethod(lambda _ms, cb: None), "quit": lambda self: None}
            )()
            self.updates = []

        def update(self, rendered):
            self.updates.append(rendered)

    barrier_cell = Position(2, 2)
    scent_cell = Position(4, 4)
    orch = type(
        "O",
        (),
        {
            "game_state": type(
                "G", (), {"own_pos": Position(1, 1), "barriers": type("BS", (), {"placed": {barrier_cell}})()}
            )(),
            "belief_map": type("B", (), {"_probabilities": {Position(1, 1): 1.0}})(),
            "scent_field": type("SF", (), {"full_field": lambda self: {scent_cell: 0.7}})(),
            "state_machine": type("S", (), {"state": "COMPUTING_MOVE"})(),
            "_last_hint_received": "quiet by the river",
        },
    )()

    monkeypatch.setattr(live_gui_mod, "LiveGuiWindow", _FakeWindow)
    session = live_gui_mod.LiveGuiSession(orch, board_size=7, poll_interval_ms=1)
    session._match_done.set()  # so the real _schedule_poll takes the "already done" branch, no recursion

    session._schedule_poll()  # the real, unmocked method

    assert session._window.updates
    rendered = session._window.updates[0]
    assert rendered.barrier_positions == frozenset({barrier_cell})
    assert scent_cell in rendered.scent_grid_colors
    assert rendered.hint_text == "quiet by the river"
