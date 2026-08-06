"""mcp_client.send_hint against a real (if lightweight) HTTP server.

Runs the server in a background thread on a genuinely free port rather than
a separate OS process — proving the HTTP round-trip works at all. The
two-process integration test (tests/integration/) is the heavier version of
this that actually proves rules 1/2 (real process separation).

A fresh, OS-assigned free port per test (rather than a hardcoded one) avoids
a real failure mode found while writing this: two tests sharing one
hardcoded port meant the second test's server silently failed to bind
(`SystemExit` in a daemon thread, swallowed as a pytest warning) and the
test only "passed" because it was accidentally served by the first test's
still-running server instead of its own.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest

from cop.tools.mcp_client import send_hint
from cop.tools.mcp_server import build_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def running_server(config):
    port = _free_port()
    mcp = build_server(config)
    thread = threading.Thread(
        target=mcp.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": port, "show_banner": False},
        daemon=True,
    )
    thread.start()
    time.sleep(0.5)  # give uvicorn a moment to bind before the test calls it
    yield f"http://127.0.0.1:{port}/mcp"


def test_send_hint_round_trips_over_real_http(running_server):
    data = asyncio.run(send_hint(running_server, "quiet by the river", "Scent strongest to the north west."))
    assert data == {"accepted": True, "word_count": 4, "scent_word_count": 6}


def test_send_hint_reports_an_over_limit_hint(running_server, config):
    over_limit_text = " ".join(["word"] * (config.hint_word_limit + 1))
    data = asyncio.run(send_hint(running_server, over_limit_text, "Scent strongest to the north west."))
    assert data["accepted"] is False
    assert data["word_count"] == config.hint_word_limit + 1
