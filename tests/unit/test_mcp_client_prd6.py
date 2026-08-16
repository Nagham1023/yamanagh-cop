"""PRD 6's client calls (`mcp_client_prd6.py`) not already exercised via
`commit_and_reveal_to_peer`'s own tests: `send_final_reveal`,
`send_capture_claim`, `send_capture_response`. `send_commit`/`send_reveal`/
`send_barrier_declaration` are exercised for real by
`test_orchestrator.py`/`test_orchestrator_commit_reveal.py`'s own live
round trips — no need to duplicate that coverage here.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from cop.tools.mcp_client_prd6 import (
    send_capture_claim,
    send_capture_response,
    send_commit,
    send_final_reveal,
    send_reveal,
)
from cop.tools.mcp_server import build_server
from cop.tools.peer_connection import PeerConnection


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_server(config) -> str:
    port = _free_port()
    mcp = build_server(config)
    threading.Thread(
        target=mcp.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": port, "show_banner": False},
        daemon=True,
    ).start()
    time.sleep(0.5)
    return f"http://127.0.0.1:{port}/mcp"


def test_send_final_reveal_round_trips_over_real_http(config):
    url = _start_server(config)
    data = asyncio.run(send_final_reveal(PeerConnection(url), {"0": "a" * 32}, {"0": False}))
    assert data == {"acknowledged": True}


def test_send_capture_claim_round_trips_over_real_http(config):
    url = _start_server(config)
    data = asyncio.run(send_capture_claim(PeerConnection(url), 3, 3, 3, 3, 7))
    assert data == {"acknowledged": True}


def test_send_capture_response_round_trips_over_real_http(config):
    url = _start_server(config)
    data = asyncio.run(send_capture_response(PeerConnection(url), True, 3, 3))
    assert data == {"acknowledged": True}


def _start_pre_prd15_server() -> str:
    """A real FastMCP server whose `receive_commit`/`receive_reveal` predate
    PRD 15 — exactly the thief repo's own shape, found live: it never asked
    for `sent_at`/`deadline_at` to be added on its own receiving side."""
    mcp = FastMCP("pre_prd15_peer")

    @mcp.tool
    def receive_commit(h_commit: str) -> dict:
        return {"acknowledged": True}

    @mcp.tool
    def receive_reveal(move: dict, hint_text: str) -> dict:
        return {"accepted": True, "word_count": len(hint_text.split())}

    port = _free_port()
    threading.Thread(
        target=mcp.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": port, "show_banner": False},
        daemon=True,
    ).start()
    time.sleep(0.5)
    return f"http://127.0.0.1:{port}/mcp"


def test_send_commit_falls_back_when_the_peer_rejects_the_new_timing_fields():
    # The real bug this closes: our own client always sends sent_at/
    # deadline_at, so it must not be permanently unable to commit to any
    # peer whose server predates PRD 15 — the fallback retry is safe here
    # specifically because FastMCP rejects before the tool body ever runs.
    url = _start_pre_prd15_server()
    data = asyncio.run(send_commit(PeerConnection(url), "a" * 64, time.time(), time.time() + 30.0))
    assert data == {"acknowledged": True}


def test_send_reveal_falls_back_when_the_peer_rejects_the_new_timing_fields():
    url = _start_pre_prd15_server()
    data = asyncio.run(
        send_reveal(
            PeerConnection(url),
            {"type": "move", "direction": "N"},
            "quiet by the river",
            time.time(),
            time.time() + 30.0,
        )
    )
    assert data == {"accepted": True, "word_count": 4}


def test_rejected_for_new_timing_fields_is_not_a_blanket_check():
    # Not a general-purpose retry classifier: only a schema rejection that
    # actually names sent_at/deadline_at counts. A real, unrelated
    # validation error (e.g. a missing h_commit) must not be misread as
    # this specific, safe-to-retry case.
    from cop.tools.mcp_client_prd6 import _rejected_for_new_timing_fields

    timing_rejection = ToolError(
        "2 validation errors for call[receive_commit]\nsent_at\n  Unexpected keyword argument "
        "[type=unexpected_keyword_argument, input_value=1.0, input_type=float]"
    )
    assert _rejected_for_new_timing_fields(timing_rejection) is True

    unrelated_rejection = ToolError("1 validation error for call[receive_commit]\nh_commit\n  Field required")
    assert _rejected_for_new_timing_fields(unrelated_rejection) is False


def test_send_commit_reraises_a_real_connection_failure_unmodified():
    # The fallback only ever catches ToolError (a schema rejection); a
    # genuine network failure (nothing listening) must propagate exactly
    # as it always did, not be swallowed by the new try/except.
    dead_port = _free_port()  # never bound — nothing listens here
    connection = PeerConnection(f"http://127.0.0.1:{dead_port}/mcp")
    with pytest.raises(Exception):  # noqa: B017 - any connection failure counts, same as elsewhere in this suite
        asyncio.run(send_commit(connection, "a" * 64, time.time(), time.time() + 30.0))
