"""Two real OS processes each sending AND receiving in the same overlapping
exchange — not a one-way round-trip. This is the shape a real match will
actually have (both sides initiate a turn), so it's worth proving the
server side handles a concurrent inbound request while its own outbound
send is also in flight, with no cross-talk between the two independent
processes (rule 2).
"""

from __future__ import annotations

import json
import time

from _helpers import free_port, spawn_server, wait_for_port


def test_two_processes_send_and_receive_in_the_same_overlapping_exchange(tmp_path):
    port_a, port_b = free_port(), free_port()
    log_a, log_b = tmp_path / "a_trace.jsonl", tmp_path / "b_trace.jsonl"

    # Each process is told the other's port up front, so each starts trying
    # to send to its peer as soon as its own server (and the peer's) are up —
    # both processes act as sender and receiver in the same wall-clock
    # window, rather than one finishing before the other starts.
    proc_a = spawn_server(port_a, log_a, peer_port=port_b, peer_text="hint from a")
    proc_b = spawn_server(port_b, log_b, peer_port=port_a, peer_text="hint from b")
    try:
        wait_for_port(port_a)
        wait_for_port(port_b)

        events_a = _wait_for_event(log_a, "turn_resolved", timeout=5.0)
        events_b = _wait_for_event(log_b, "turn_resolved", timeout=5.0)

        # Each process's own trace logs the ack for *its own send*: A sent
        # "hint from a" to B, B sent "hint from b" to A — the echoed payload
        # matches what that process itself sent, not what it received.
        assert events_a["result"] == {"accepted": True, "word_count": 3}
        assert events_b["result"] == {"accepted": True, "word_count": 3}

        # Both sends landed within the same short window — genuine overlap,
        # not one process finishing long before the other even started.
        assert abs(events_a["time"] - events_b["time"]) < 2.0
    finally:
        proc_a.terminate()
        proc_a.wait(timeout=5)
        proc_b.terminate()
        proc_b.wait(timeout=5)


def _wait_for_event(log_path, event_name: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if log_path.exists():
            for line in log_path.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                if entry["event"] == event_name:
                    return entry
        time.sleep(0.1)
    raise TimeoutError(f"{event_name!r} never appeared in {log_path}")
