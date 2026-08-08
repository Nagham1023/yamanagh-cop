"""PRD 9's one new client call, `send_step0` (`mcp_client_prd9.py`) — a
real HTTP round trip, same pattern `test_mcp_client_prd6.py` already uses.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

from cop.tools.mcp_client_prd9 import send_step0
from cop.tools.mcp_server import build_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_server(config, **build_kwargs) -> str:
    port = _free_port()
    mcp = build_server(config, **build_kwargs)
    threading.Thread(
        target=mcp.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": port, "show_banner": False},
        daemon=True,
    ).start()
    time.sleep(0.5)
    return f"http://127.0.0.1:{port}/mcp"


def test_send_step0_round_trips_over_real_http(config):
    def _on_step0(declaration, signature, repos):
        return {
            "declaration": {"group_name": "responder"},
            "signature": "responder-sig",
            "repos": {"cop": "https://example.com/cop"},
        }

    url = _start_server(config, on_step0=_on_step0)
    data = asyncio.run(
        send_step0(url, {"group_name": "initiator"}, "initiator-sig", {"cop": "https://example.com/other"})
    )

    assert data == {
        "declaration": {"group_name": "responder"},
        "signature": "responder-sig",
        "repos": {"cop": "https://example.com/cop"},
    }
