"""std_v1/replay_viewer.py tests (rule 20 **[FATAL]**) — `StdV1ReplayViewer`
must expose the same clean-pass / halt-on-tamper behavior as the native
`ReplayViewer`, since one `ReplayViewerWindow` drives both. The rejection
path (tampered step halts navigation) is as load-bearing as the honest
one, matching this project's own "a verifier that never rejects anything
is worthless" rule.
"""

from __future__ import annotations

import json
import tkinter

import pytest

from cop.observability.replay_viewer import ReplayViewerWindow
from cop.std_v1.replay_log import merge_records, write_sub_game_log
from cop.std_v1.replay_viewer import StdV1ReplayViewer
from cop.std_v1.sealing import build_audit_record, build_turn_payload, seal_turn


def _display_available() -> bool:
    try:
        root = tkinter.Tk()
        root.destroy()
        return True
    except tkinter.TclError:
        return False


_HAS_DISPLAY = _display_available()


def _sealed_record(step: int, sender: str) -> tuple[dict, str]:
    payload = build_turn_payload(step=step, sender=sender, move="N", hint="", smell_grid={})
    sealed = seal_turn(payload)
    return build_audit_record(payload, sealed["nonce"]), sealed["commit"]


def _two_step_log(tmp_path, *, tamper_step_2: bool = False):
    my_record, my_commit = _sealed_record(1, "police")
    peer_record, peer_commit = _sealed_record(2, "thief")
    merged = merge_records([my_record], {1: my_commit}, [peer_record], {2: peer_commit})
    log_path = write_sub_game_log("dev-team-vs-thief-team", 1, merged, tmp_path)

    if tamper_step_2:
        data = json.loads(log_path.read_text(encoding="utf-8"))
        for record in data["records"]:
            if record["step"] == 2:
                record["move"] = "TAMPERED"
        log_path.write_text(json.dumps(data), encoding="utf-8")

    return log_path


def test_a_clean_std_v1_log_shows_verified_ok(tmp_path):
    log_path = _two_step_log(tmp_path)

    viewer = StdV1ReplayViewer(log_path)

    assert viewer.overall_status == "Verified OK"
    assert viewer.passed is True
    assert len(viewer.steps) == 2
    assert viewer.halted is False


def test_a_tampered_std_v1_log_shows_tampered_and_halts_at_that_step(tmp_path):
    log_path = _two_step_log(tmp_path, tamper_step_2=True)

    viewer = StdV1ReplayViewer(log_path)

    assert viewer.overall_status == "TAMPERED"
    assert viewer.passed is False
    assert viewer.current().step == 1
    assert viewer.halted is False  # step 1 itself is clean

    viewer.step_forward()
    assert viewer.current().step == 2
    assert viewer.current().verified is False
    assert viewer.halted is True


def test_step_forward_never_advances_past_the_first_tampered_std_v1_step(tmp_path):
    log_path = _two_step_log(tmp_path, tamper_step_2=True)
    viewer = StdV1ReplayViewer(log_path)

    viewer.step_forward()
    assert viewer.halted is True
    for _ in range(3):
        viewer.step_forward()
        assert viewer.current().step == 2  # never advances past it


def test_step_backward_from_the_halted_std_v1_step_is_unrestricted(tmp_path):
    log_path = _two_step_log(tmp_path, tamper_step_2=True)
    viewer = StdV1ReplayViewer(log_path)
    viewer.step_forward()
    assert viewer.halted is True

    backed = viewer.step_backward()
    assert backed.step == 1
    assert viewer.halted is False


def test_a_std_v1_log_with_no_records_reports_no_current_step(tmp_path):
    log_path = write_sub_game_log("dev-team-vs-thief-team", 1, [], tmp_path)

    viewer = StdV1ReplayViewer(log_path)

    assert viewer.overall_status == "Verified OK"  # vacuously — no records to mismatch
    assert viewer.current() is None


@pytest.mark.skipif(not _HAS_DISPLAY, reason="no display available for a real Tk window")
def test_replay_viewer_window_works_with_a_std_v1_viewer(tmp_path):
    log_path = _two_step_log(tmp_path, tamper_step_2=True)
    viewer = StdV1ReplayViewer(log_path)

    window = ReplayViewerWindow(viewer)
    try:
        assert window.banner.cget("text") == "TAMPERED"
        assert window.banner.cget("fg") == "red"
        assert str(window.forward_button.cget("state")) == "normal"
        window._forward()
        assert str(window.forward_button.cget("state")) == "disabled"
        assert "blocked" in window.step_label.cget("text")
        step_before = viewer.current().step
        window._forward()  # a real click while disabled must still be a no-op
        assert viewer.current().step == step_before
    finally:
        window.close()
