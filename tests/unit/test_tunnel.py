"""tools/tunnel.py: parses a real ngrok admin-API shape against a local
stand-in server — the real `ngrok` binary isn't installed in this dev
environment (confirmed absent, TODO5 §0), so the polling/parsing logic is
proven independently of actually having it available.
"""

from __future__ import annotations

import json
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from cop.tools.tunnel import start_tunnel, stop_tunnel

_PLACEHOLDER_COMMAND = [sys.executable, "-c", "import time; time.sleep(60)"]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _admin_api_stub(tunnels_body: dict) -> tuple[str, HTTPServer]:
    """A tiny local HTTP server standing in for ngrok's own local admin
    API, returning a canned response instead of a real tunnel list."""

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's naming
            body = json.dumps(tunnels_body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:  # silence stderr noise per-request
            pass

    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}/api/tunnels", server


def test_start_tunnel_parses_a_real_ngrok_admin_api_response():
    admin_api_url, server = _admin_api_stub(
        {"tunnels": [{"proto": "https", "public_url": "https://abc123.ngrok-free.app"}]}
    )
    try:
        tunnel = start_tunnel(8000, admin_api_url=admin_api_url, command=_PLACEHOLDER_COMMAND)
        assert tunnel.public_url == "https://abc123.ngrok-free.app"
        stop_tunnel(tunnel)
    finally:
        server.shutdown()


def test_start_tunnel_ignores_a_non_https_tunnel_entry():
    # ngrok's admin API can list an http tunnel alongside the https one —
    # only the https URL is the one worth exposing.
    admin_api_url, server = _admin_api_stub(
        {
            "tunnels": [
                {"proto": "http", "public_url": "http://abc123.ngrok-free.app"},
                {"proto": "https", "public_url": "https://abc123.ngrok-free.app"},
            ]
        }
    )
    try:
        tunnel = start_tunnel(8000, admin_api_url=admin_api_url, command=_PLACEHOLDER_COMMAND)
        assert tunnel.public_url == "https://abc123.ngrok-free.app"
        stop_tunnel(tunnel)
    finally:
        server.shutdown()


def test_start_tunnel_raises_a_clear_error_when_ngrok_is_not_on_path():
    # Real absence, not simulated — confirmed in TODO5 §0.
    with pytest.raises(RuntimeError, match="ngrok is not installed"):
        start_tunnel(8000)


def test_start_tunnel_times_out_when_the_admin_api_never_reports_a_tunnel():
    admin_api_url, server = _admin_api_stub({"tunnels": []})
    try:
        with pytest.raises(TimeoutError):
            start_tunnel(
                8000, admin_api_url=admin_api_url, timeout_seconds=0.5, command=_PLACEHOLDER_COMMAND
            )
    finally:
        server.shutdown()


def test_start_tunnel_times_out_when_the_admin_api_is_unreachable():
    with pytest.raises(TimeoutError):
        start_tunnel(
            8000,
            admin_api_url="http://127.0.0.1:1/api/tunnels",  # nothing listens on port 1
            timeout_seconds=0.5,
            command=_PLACEHOLDER_COMMAND,
        )
