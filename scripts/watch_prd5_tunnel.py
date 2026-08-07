"""Watch PRD 5's milestone run live: two sections. Section 1 proves
`tools/tunnel.py`'s admin-API parsing logic against a local stand-in (no
real `ngrok` binary needed — see PRD-5-cloud-exposure.md's "New
dependency" section for why). Section 2 demonstrates caller-IP capture
over one real HTTP round-trip, with a manually-set `X-Forwarded-For`
header standing in for what a real tunnel would insert, printing the
`connection_received` log entry so a human can see the non-loopback
address land exactly as the milestone's own verification method expects.

The real milestone itself — a genuinely remote machine connecting through
a real ngrok tunnel — needs a human with an ngrok account and a second
network; see PRD-5-cloud-exposure.md's Milestone section and TODO5.md §7.

Run:
    uv run python scripts/watch_prd5_tunnel.py
"""

from __future__ import annotations

import asyncio
import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tests" / "integration"))

from _helpers import REPO_CONFIG  # noqa: E402

from cop.orchestrator import Orchestrator  # noqa: E402
from cop.reasoning.cop_brain import CopBrain  # noqa: E402
from cop.shared.config import GameConfig  # noqa: E402
from cop.tools.mcp_client_prd6 import send_reveal  # noqa: E402
from cop.tools.tunnel import start_tunnel, stop_tunnel  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _admin_api_stub(public_url: str) -> tuple[str, HTTPServer]:
    """A tiny local HTTP server standing in for ngrok's own local admin
    API — see PRD-5-cloud-exposure.md: the real binary isn't installed in
    every dev environment, so the parsing logic is proven independently."""

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = json.dumps({"tunnels": [{"proto": "https", "public_url": public_url}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:
            pass

    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}/api/tunnels", server


def section_1_tunnel_wrapper_local() -> None:
    print("1. tools/tunnel.py against a local admin-API stand-in (no real ngrok needed)")
    admin_api_url, admin_server = _admin_api_stub("https://demo123.ngrok-free.app")
    try:
        placeholder_command = [sys.executable, "-c", "import time; time.sleep(30)"]
        tunnel = start_tunnel(_free_port(), admin_api_url=admin_api_url, command=placeholder_command)
        print(f"  start_tunnel resolved public_url = {tunnel.public_url!r}")
        stop_tunnel(tunnel)
        print(f"  stop_tunnel terminated the process: poll() = {tunnel.process.poll()}")
    finally:
        admin_server.shutdown()


def section_2_ip_capture_over_real_http() -> None:
    print("\n2. Caller-IP capture over a real HTTP round-trip")
    config = GameConfig.from_file(REPO_CONFIG)
    log_path = Path("/tmp/watch_prd5_trace.jsonl")
    log_path.unlink(missing_ok=True)
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(log_path))
    port = _free_port()
    threading.Thread(
        target=orchestrator.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)
    print(f"  peer listening on 127.0.0.1:{port}")

    print("\n  a) no forwarding header (direct call, no tunnel in front):")
    asyncio.run(
        send_reveal(
            f"http://127.0.0.1:{port}/mcp", {"type": "move", "direction": "NORTH"}, "quiet by the river"
        )
    )

    print("  b) with X-Forwarded-For set (what a real tunnel would insert):")
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    async def _call_with_forwarded_header() -> None:
        transport = StreamableHttpTransport(
            f"http://127.0.0.1:{port}/mcp", headers={"X-Forwarded-For": "203.0.113.7"}
        )
        async with Client(transport) as client:
            await client.call_tool(
                "receive_reveal",
                {"move": {"type": "move", "direction": "NORTH"}, "hint_text": "a test hint"},
            )

    asyncio.run(_call_with_forwarded_header())

    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    connection_events = [e for e in events if e["event"] == "connection_received"]
    print("\n  connection_received log entries:")
    for event in connection_events:
        print(f"    ip={event['ip']!r}")
    print(
        "\n  (b)'s address is non-loopback and non-LAN-local — exactly what the real milestone's "
        "verification method (grep the log for a non-127.0.0.1, non-192.168.x.x/10.x.x.x address) checks for."
    )


def main() -> None:
    section_1_tunnel_wrapper_local()
    section_2_ip_capture_over_real_http()
    print("\nAll PRD 5 automatable behaviours ran end-to-end. The real remote-machine milestone is a human-run step — see TODO5.md §7.")


if __name__ == "__main__":
    main()
