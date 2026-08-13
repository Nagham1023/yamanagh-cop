"""Rule 20 **[FATAL]**: the Replay Viewer must show `Verified OK` on a clean
log and **reject** (`TAMPERED`) a tampered one — both paths tested, not
just the honest one, matching this project's own "a verifier that never
rejects anything is worthless" rule.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
import tkinter

import pytest

from cop.observability.replay_viewer import ReplayViewer, ReplayViewerWindow, nonces_from_log
from cop.orchestrator import Orchestrator
from cop.reasoning.brain_base import Move
from cop.reasoning.cop_brain import CopBrain


def _display_available() -> bool:
    try:
        root = tkinter.Tk()
        root.destroy()
        return True
    except tkinter.TclError:
        return False


_HAS_DISPLAY = _display_available()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_one_real_committed_turn(config, tmp_path) -> Orchestrator:
    port = _free_port()
    server = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "server_trace.jsonl"))
    threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.state_machine.transition("COMPUTING_MOVE")
    asyncio.run(
        client.commit_and_reveal_to_peer(
            f"http://127.0.0.1:{port}/mcp", Move(direction="N"), False, "quiet by the river"
        )
    )
    return client


def test_a_genuine_untampered_log_shows_verified_ok(config, tmp_path):
    client = _run_one_real_committed_turn(config, tmp_path)

    viewer = ReplayViewer(tmp_path / "client_trace.jsonl", client._pending_nonces)

    assert viewer.overall_status == "Verified OK"
    assert viewer.audit_result.passed is True
    assert len(viewer.steps) == 1
    assert viewer.current().verified is True


def test_a_tampered_log_shows_tampered_and_the_step_is_flagged(config, tmp_path):
    client = _run_one_real_committed_turn(config, tmp_path)
    trace_path = tmp_path / "client_trace.jsonl"

    lines = trace_path.read_text(encoding="utf-8").splitlines()
    tampered_lines = []
    for line in lines:
        entry = json.loads(line)
        if entry["event"] == "committing":
            entry["move"] = {"type": "move", "direction": "S"}  # tampered after commit
        tampered_lines.append(json.dumps(entry))
    trace_path.write_text("\n".join(tampered_lines) + "\n", encoding="utf-8")

    viewer = ReplayViewer(trace_path, client._pending_nonces)

    assert viewer.overall_status == "TAMPERED"
    assert viewer.audit_result.passed is False
    assert viewer.current().verified is False


def test_halted_is_false_throughout_a_clean_log(config, tmp_path):
    client = _run_one_real_committed_turn(config, tmp_path)
    viewer = ReplayViewer(tmp_path / "client_trace.jsonl", client._pending_nonces)

    assert viewer.halted is False
    viewer.step_forward()
    assert viewer.halted is False


def test_step_forward_never_advances_past_the_first_tampered_step(config, tmp_path):
    client = _run_two_real_committed_turns(config, tmp_path)
    trace_path = tmp_path / "client_trace.jsonl"

    lines = trace_path.read_text(encoding="utf-8").splitlines()
    tampered_lines = []
    for line in lines:
        entry = json.loads(line)
        if entry["event"] == "committing" and entry["step"] == 2:
            entry["move"] = {"type": "move", "direction": "S"}  # only the SECOND step is tampered
        tampered_lines.append(json.dumps(entry))
    trace_path.write_text("\n".join(tampered_lines) + "\n", encoding="utf-8")

    viewer = ReplayViewer(trace_path, client._pending_nonces)
    assert viewer.current().step == 1
    assert viewer.halted is False  # step 1 itself is clean

    viewer.step_forward()
    assert viewer.current().step == 2
    assert viewer.current().verified is False
    assert viewer.halted is True  # arrived at the first tampered step

    # Further Forward presses must not advance beyond it, repeatedly.
    for _ in range(3):
        viewer.step_forward()
        assert viewer.current().step == 2


def test_step_backward_from_the_halted_step_is_unrestricted(config, tmp_path):
    client = _run_two_real_committed_turns(config, tmp_path)
    trace_path = tmp_path / "client_trace.jsonl"
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    tampered_lines = []
    for line in lines:
        entry = json.loads(line)
        if entry["event"] == "committing" and entry["step"] == 2:
            entry["move"] = {"type": "move", "direction": "S"}
        tampered_lines.append(json.dumps(entry))
    trace_path.write_text("\n".join(tampered_lines) + "\n", encoding="utf-8")

    viewer = ReplayViewer(trace_path, client._pending_nonces)
    viewer.step_forward()
    assert viewer.halted is True

    backed = viewer.step_backward()
    assert backed.step == 1
    assert viewer.halted is False  # reviewing before the tamper point is unrestricted


@pytest.mark.skipif(not _HAS_DISPLAY, reason="no display available for a real Tk window")
def test_replay_viewer_window_disables_forward_at_the_tampered_step(config, tmp_path):
    client = _run_two_real_committed_turns(config, tmp_path)
    trace_path = tmp_path / "client_trace.jsonl"
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    tampered_lines = []
    for line in lines:
        entry = json.loads(line)
        if entry["event"] == "committing" and entry["step"] == 2:
            entry["move"] = {"type": "move", "direction": "S"}
        tampered_lines.append(json.dumps(entry))
    trace_path.write_text("\n".join(tampered_lines) + "\n", encoding="utf-8")

    viewer = ReplayViewer(trace_path, client._pending_nonces)
    window = ReplayViewerWindow(viewer)
    try:
        assert str(window.forward_button.cget("state")) == "normal"
        window._forward()
        assert str(window.forward_button.cget("state")) == "disabled"
        assert "blocked" in window.step_label.cget("text")
        step_before = viewer.current().step
        window._forward()  # a real click while disabled must still be a no-op at the model level
        assert viewer.current().step == step_before
    finally:
        window.close()


def test_step_navigation_does_not_recompute_the_audit(config, tmp_path):
    client = _run_one_real_committed_turn(config, tmp_path)
    viewer = ReplayViewer(tmp_path / "client_trace.jsonl", client._pending_nonces)
    original_result = viewer.audit_result

    viewer.step_forward()  # only one step exists — stays put
    viewer.step_backward()

    assert viewer.audit_result is original_result  # same object, never recomputed


@pytest.mark.skipif(not _HAS_DISPLAY, reason="no display available for a real Tk window")
def test_replay_viewer_window_shows_the_right_banner_color(config, tmp_path):
    client = _run_one_real_committed_turn(config, tmp_path)
    viewer = ReplayViewer(tmp_path / "client_trace.jsonl", client._pending_nonces)

    window = ReplayViewerWindow(viewer)
    try:
        assert window.banner.cget("text") == "Verified OK"
        assert window.banner.cget("fg") == "green"
    finally:
        window.close()


def _run_two_real_committed_turns(config, tmp_path) -> Orchestrator:
    """Two consecutive `commit_and_reveal_to_peer` calls, each preceded by a
    real `game_state.apply()` — matching `take_turn()`'s own real ordering
    (apply, then commit). Skipping the `apply()` call, as the single-turn
    fixture above does, would leave `steps_taken` at `0` for both commits —
    a genuine step-number collision that silently overwrites the first
    call's `_pending_nonces` entry with the second's, turning the audit's
    honest first step into a false `Hcommit mismatch` (the same off-by-one
    class of bug `integrity/peer_trace.py`'s own fixture already hit).
    `E` twice (never `N`) — `cop_start` is a board corner where `N` is off-
    board and `game_state.apply()` raises on an illegal move, unlike the
    unvalidated self-audit path the single-turn fixture above relies on."""
    port = _free_port()
    server = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "server_trace.jsonl"))
    threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    url = f"http://127.0.0.1:{port}/mcp"
    for _ in range(2):
        move = Move(direction="E")
        client.game_state.apply(move, client.board)
        client.state_machine.transition("COMPUTING_MOVE")
        asyncio.run(client.commit_and_reveal_to_peer(url, move, False, "quiet by the river"))
        # commit_and_reveal_to_peer's own internal transitions already land
        # back on WAITING_FOR_OPPONENT — ready for the next COMPUTING_MOVE.
    return client


def test_step_forward_and_backward_actually_move_the_index_across_two_real_steps(config, tmp_path):
    client = _run_two_real_committed_turns(config, tmp_path)
    viewer = ReplayViewer(tmp_path / "client_trace.jsonl", client._pending_nonces)

    assert len(viewer.steps) == 2
    assert viewer.current().step == 1

    forwarded = viewer.step_forward()
    assert forwarded.step == 2
    assert viewer.step_forward().step == 2  # already at the last step — stays put

    backed = viewer.step_backward()
    assert backed.step == 1
    assert viewer.step_backward().step == 1  # already at the first step — stays put


def test_a_log_with_no_committed_steps_reports_no_current_step(tmp_path):
    empty_log = tmp_path / "empty_trace.jsonl"
    empty_log.write_text("", encoding="utf-8")

    viewer = ReplayViewer(empty_log, {})

    assert viewer.overall_status == "Verified OK"  # vacuously — no commit entries to mismatch
    assert viewer.current() is None


def _run_one_turn_and_final_reveal(config, tmp_path) -> Orchestrator:
    """Like `_run_one_real_committed_turn`, but also sends Final Reveal —
    the only thing that produces a `nonces_revealed` trace entry
    (`orchestrator_peer_audit.py`, PRD 10)."""
    port = _free_port()
    server = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "server_trace.jsonl"))
    threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    url = f"http://127.0.0.1:{port}/mcp"
    client.state_machine.transition("COMPUTING_MOVE")
    asyncio.run(client.commit_and_reveal_to_peer(url, Move(direction="N"), False, "quiet by the river"))
    asyncio.run(client.send_final_reveal_to_peer(url))
    return client


def test_nonces_from_log_matches_the_process_own_pending_nonces(config, tmp_path):
    client = _run_one_turn_and_final_reveal(config, tmp_path)

    extracted = nonces_from_log(tmp_path / "client_trace.jsonl")

    expected = {str(step): nonce for step, nonce in client._pending_nonces.items()}
    assert extracted == expected
    assert extracted  # not vacuously empty — a real turn really happened


def test_nonces_from_log_round_trips_through_a_real_replay_verification(config, tmp_path):
    _run_one_turn_and_final_reveal(config, tmp_path)
    log_path = tmp_path / "client_trace.jsonl"

    viewer = ReplayViewer(log_path, nonces_from_log(log_path))

    assert viewer.overall_status == "Verified OK"


def test_nonces_from_log_rejects_a_log_with_no_final_reveal(config, tmp_path):
    # A match that never reached Final Reveal (crashed, or was never
    # finished) genuinely has no revealed nonces to recover — a clear
    # error, not a silent empty dict or a crash.
    _run_one_real_committed_turn(config, tmp_path)

    with pytest.raises(ValueError, match="nonces_revealed"):
        nonces_from_log(tmp_path / "client_trace.jsonl")


@pytest.mark.skipif(not _HAS_DISPLAY, reason="no display available for a real Tk window")
def test_replay_viewer_window_forward_and_back_buttons_update_the_step_label(config, tmp_path):
    client = _run_two_real_committed_turns(config, tmp_path)
    viewer = ReplayViewer(tmp_path / "client_trace.jsonl", client._pending_nonces)

    window = ReplayViewerWindow(viewer)
    try:
        assert window.step_label.cget("text") == "step 1: ok"
        window._forward()
        assert window.step_label.cget("text") == "step 2: ok"
        window._back()
        assert window.step_label.cget("text") == "step 1: ok"
    finally:
        window.close()


@pytest.mark.skipif(not _HAS_DISPLAY, reason="no display available for a real Tk window")
def test_replay_viewer_window_with_no_committed_steps_shows_the_placeholder_label(tmp_path):
    empty_log = tmp_path / "empty_trace.jsonl"
    empty_log.write_text("", encoding="utf-8")
    viewer = ReplayViewer(empty_log, {})

    window = ReplayViewerWindow(viewer)
    try:
        assert window.step_label.cget("text") == "(no committed steps in this log)"
    finally:
        window.close()
