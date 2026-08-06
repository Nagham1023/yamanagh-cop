"""Programmatic ngrok tunnel wrapper (rule 10 — expose the local server to
the public internet via a tunneling tool; PRD 5).

Shells out to the real `ngrok` binary (`subprocess.Popen`, same pattern
this repo already uses for spawning real OS-process peers in
`tests/integration/_server_process.py`) rather than adding a Python
wrapper package — `httpx` (already a dependency, PRD 4) is all that's
needed to poll ngrok's own local admin API for the assigned public URL.
ngrok chosen over Localtonet as the concrete implementation; the book
permits either (PRD-5-cloud-exposure.md Build section).
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass

import httpx

_DEFAULT_ADMIN_API_URL = "http://127.0.0.1:4040/api/tunnels"
_POLL_INTERVAL_SECONDS = 0.2


@dataclass
class Tunnel:
    process: subprocess.Popen
    public_url: str


def start_tunnel(
    port: int,
    admin_api_url: str = _DEFAULT_ADMIN_API_URL,
    timeout_seconds: float = 10.0,
    command: list[str] | None = None,
) -> Tunnel:
    """Launch `ngrok http <port>` and poll its local admin API
    (`admin_api_url`) until a public HTTPS tunnel is reported.

    `admin_api_url` and `command` are both parameters, not hardcoded,
    specifically so a test can point the poll at a local stand-in server
    and launch a harmless placeholder process — the real `ngrok` binary
    isn't installed in every dev/CI environment, so the polling/parsing
    logic is tested independently of actually having it available (found
    necessary while writing the tests: without a `command` override, every
    test would hit the same immediate "ngrok not found" error the real
    absence produces, with no way to exercise the polling logic at all).
    """
    try:
        process = subprocess.Popen(
            command or ["ngrok", "http", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "ngrok is not installed or not on PATH — install it separately "
            "(https://ngrok.com/download); this repo only shells out to it, "
            "it is not a Python dependency"
        ) from exc

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = httpx.get(admin_api_url, timeout=1.0)
            response.raise_for_status()
            for candidate in response.json().get("tunnels", []):
                if candidate.get("proto") == "https":
                    return Tunnel(process=process, public_url=candidate["public_url"])
        except httpx.HTTPError:
            pass
        time.sleep(_POLL_INTERVAL_SECONDS)

    process.terminate()
    raise TimeoutError(f"ngrok admin API at {admin_api_url!r} never reported a public HTTPS tunnel")


def stop_tunnel(tunnel: Tunnel) -> None:
    """Terminate the tunnel process, waiting with a bounded timeout."""
    tunnel.process.terminate()
    tunnel.process.wait(timeout=5)
