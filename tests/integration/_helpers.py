"""Shared spawn/wait helpers for the two-process integration suite.

Extracted so test_two_process_roundtrip.py, test_concurrent_exchange.py, and
`_server_process.py` don't each reinvent "wait for a real OS process's port
to come up" — the "extract a shared helper" split named in CLAUDE.md's
150-line house rule.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

HELPER = Path(__file__).parent / "_server_process.py"
REPO_CONFIG = str(
    Path(__file__).resolve().parent.parent.parent / "config" / "shared" / "config_dev_g01.json"
)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_port(port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"server on port {port} never came up")


def spawn_server(
    port: int,
    log_path: Path,
    peer_port: int | None = None,
    peer_text: str = "a test hint",
    peer_scent_report: str = "Scent strongest to the north west.",
) -> subprocess.Popen:
    """Launch `_server_process.py` as a real OS process.

    `peer_port` is optional: when given, the spawned process, once its own
    server is up, also sends `peer_text`/`peer_scent_report` to that peer
    port — letting a process act as sender and receiver in the same run,
    for the overlapping-exchange test.
    """
    args = [
        sys.executable, str(HELPER),
        "--port", str(port),
        "--log-path", str(log_path),
        "--config", REPO_CONFIG,
    ]
    if peer_port is not None:
        args += [
            "--peer-port", str(peer_port),
            "--peer-text", peer_text,
            "--peer-scent-report", peer_scent_report,
        ]
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
