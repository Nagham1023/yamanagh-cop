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

from cop.tools.mcp_client_prd6 import send_capture_claim, send_capture_response, send_final_reveal
from cop.tools.mcp_server import build_server


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
    data = asyncio.run(send_final_reveal(url, {"0": "a" * 32}))
    assert data == {"acknowledged": True}


def test_send_capture_claim_round_trips_over_real_http(config):
    url = _start_server(config)
    data = asyncio.run(send_capture_claim(url, 3, 3, 3, 3, 7))
    assert data == {"acknowledged": True}


def test_send_capture_response_round_trips_over_real_http(config):
    url = _start_server(config)
    data = asyncio.run(send_capture_response(url, True, 3, 3))
    assert data == {"acknowledged": True}
