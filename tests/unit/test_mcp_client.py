"""mcp_client.send_hint/request_scent_map against a real (if lightweight)
HTTP server.

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
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from cop.domain.board import Position
from cop.tools.mcp_client import request_scent_map, send_hint
from cop.tools.mcp_server import build_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_server(config, **build_kwargs) -> str:
    port = _free_port()
    mcp = build_server(config, **build_kwargs)
    thread = threading.Thread(
        target=mcp.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": port, "show_banner": False},
        daemon=True,
    )
    thread.start()
    time.sleep(0.5)  # give uvicorn a moment to bind before the test calls it
    return f"http://127.0.0.1:{port}/mcp"


@pytest.fixture
def running_server(config):
    yield _start_server(config)


def test_send_hint_round_trips_over_real_http(running_server):
    data = asyncio.run(send_hint(running_server, "quiet by the river"))
    assert data == {"accepted": True, "word_count": 4}


def test_send_hint_reports_an_over_limit_hint(running_server, config):
    over_limit_text = " ".join(["word"] * (config.hint_word_limit + 1))
    data = asyncio.run(send_hint(running_server, over_limit_text))
    assert data["accepted"] is False
    assert data["word_count"] == config.hint_word_limit + 1


def test_request_scent_map_round_trips_over_real_http(config):
    field_data = {Position(1, 1): 0.9, Position(2, 2): 0.42}
    url = _start_server(config, get_scent_field=lambda: field_data)

    result = asyncio.run(request_scent_map(url))

    assert result == field_data


def test_request_scent_map_is_empty_over_real_http_with_no_hook(running_server):
    result = asyncio.run(request_scent_map(running_server))
    assert result == {}


def test_on_receive_gets_the_loopback_address_over_real_http_with_no_forwarding_header(config):
    received_ips = []
    url = _start_server(config, on_receive=lambda ip: received_ips.append(ip))

    asyncio.run(send_hint(url, "quiet by the river"))

    assert received_ips == ["127.0.0.1"]


def test_on_receive_prefers_x_forwarded_for_over_the_raw_loopback_address(config):
    # The actual proof the milestone's IP-logging depends on: a tunnel
    # inserts this header with the true remote caller, which must win over
    # the raw ASGI client address (always 127.0.0.1 once a tunnel is in
    # front — see mcp_server.py's _caller_ip docstring).
    received_ips = []
    url = _start_server(config, on_receive=lambda ip: received_ips.append(ip))

    async def _call_with_forwarded_header():
        transport = StreamableHttpTransport(url, headers={"X-Forwarded-For": "203.0.113.7"})
        async with Client(transport) as client:
            await client.call_tool("receive_hint", {"text": "quiet by the river"})

    asyncio.run(_call_with_forwarded_header())

    assert received_ips == ["203.0.113.7"]
