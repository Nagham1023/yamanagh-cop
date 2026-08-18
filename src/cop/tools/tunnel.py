"""Programmatic ngrok tunnel wrapper (rule 10 — expose the local server to
the public internet via a tunneling tool; PRD 5).

Shells out to the real `ngrok` binary (`subprocess.Popen`, same pattern
this repo already uses for spawning real OS-process peers in
`tests/integration/_server_process.py`) rather than adding a Python
wrapper package — `httpx` (already a dependency, PRD 4) is all that's
needed to poll ngrok's own local admin API for the assigned public URL.
ngrok chosen over Localtonet as the concrete implementation; the book
permits either (PRD-5-cloud-exposure.md Build section).

`start_tunnel` itself lives in `tunnel_start.py` (split out once it grew
past the 150-line house cap) — imports `Tunnel`/`_ngrok_command` from
here, so callers reach it via `from .tools.tunnel_start import
start_tunnel` rather than through this module, keeping the dependency
one-directional (no circular import between the two files).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

_DEFAULT_ADMIN_API_URL = "http://127.0.0.1:4040/api/tunnels"
_POLL_INTERVAL_SECONDS = 0.2


@dataclass
class Tunnel:
    process: subprocess.Popen
    public_url: str
    log_file: object | None = None  # the open file handle backing ngrok's own stdout/stderr, if any


def _ngrok_command(port: int, domain: str | None) -> list[str]:
    """Pure, independently testable: `ngrok`'s real binary isn't installed
    in every dev/CI environment (TODO5 §0), so the command-construction
    logic is proven on its own rather than only by inspecting a real
    subprocess launch."""
    command = ["ngrok", "http"]
    if domain is not None:
        command.append(f"--domain={domain}")
    command.append(str(port))
    return command


def stop_tunnel(tunnel: Tunnel) -> None:
    """Terminate the tunnel process, waiting with a bounded timeout, then
    force-killing rather than letting `TimeoutExpired` propagate — found
    live: cloudflared (reused through this same provider-agnostic `Tunnel`
    shape) didn't always honor SIGTERM within 5s, and the resulting
    exception, raised from inside `run_std_v1_peer`'s own `finally` block,
    replaced the real match-ending error in the traceback entirely (a
    genuine rule-3 terms mismatch, in the one case that surfaced this)."""
    tunnel.process.terminate()
    try:
        tunnel.process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        tunnel.process.kill()
        tunnel.process.wait(timeout=5)
    if tunnel.log_file is not None:
        tunnel.log_file.close()
