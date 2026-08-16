"""Cloudflare Quick Tunnel wrapper (rule 10's tunnel requirement) — an
alternative to `tools/tunnel.py`'s ngrok, tried because ngrok's free-tier
connection-rate cap was diagnosed as the real cause of a recurring
round-26/27 match failure (a request-volume problem, not a code bug on
either peer). Shells out to the real `cloudflared` binary, same subprocess
pattern `tunnel.py` already uses.

No local admin API to poll (unlike ngrok) — confirmed empirically against
the real binary: `cloudflared tunnel --url <addr>` writes everything,
including the assigned public URL, to its own stderr; stdout stays silent.
A background thread reads stderr lines into a queue; the main thread polls
that queue against a deadline, mirroring `tunnel_start.py`'s own polling
loop shape.

A quick tunnel has no reserved/stable domain — that needs a paid-adjacent
named tunnel plus a Cloudflare-managed DNS zone, a bigger, separate setup
step nobody has opted into yet. Every launch gets a brand-new random
`*.trycloudflare.com` URL, so there's no ngrok-style "domain already
claimed" collision to guard against, and no `domain=` parameter here.

`Tunnel`/`stop_tunnel` (`tunnel.py`) are provider-agnostic in shape (just a
process, a public URL, and an optional log file) — reused as-is rather
than duplicated.
"""

from __future__ import annotations

import queue
import re
import subprocess
import threading
import time

from .tunnel import Tunnel

_URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def _cloudflared_command(port: int) -> list[str]:
    """Pure, independently testable — same reasoning as `tunnel.py`'s own
    `_ngrok_command`: the real `cloudflared` binary isn't installed in
    every dev/CI environment."""
    return ["cloudflared", "tunnel", "--url", f"http://localhost:{port}", "--loglevel", "info"]


def _stream_lines(pipe, line_queue: queue.Queue) -> None:
    """Runs on a background thread: a blocking `readline()` can't itself
    be bounded by a deadline, so this feeds a queue the main thread polls
    instead — the same cross-thread bridging shape `_watch_loop`
    (`orchestrator_server.py`) already uses elsewhere in this repo."""
    for line in iter(pipe.readline, ""):
        line_queue.put(line)


def start_cloudflare_tunnel(
    port: int,
    timeout_seconds: float = 25.0,
    command: list[str] | None = None,
    log_path: str | None = None,
) -> Tunnel:
    """Launch `cloudflared tunnel --url http://localhost:<port>` and watch
    its own stderr until the assigned public `*.trycloudflare.com` URL
    appears. Slower to report than ngrok in practice — a real local run
    took ~5s to the URL line and several more before cloudflared's own
    connectivity pre-checks finished — hence the longer default timeout
    than `start_tunnel`'s own 10s, not an arbitrary bump.

    `log_path`: same reasoning as `tunnel_start.py`'s own parameter —
    cloudflared's own diagnostic output captured for later debugging
    instead of discarded; `None` keeps it uncaptured (tests use a
    placeholder `command`, same convention as the ngrok tests)."""
    command = command or _cloudflared_command(port)
    log_file = open(log_path, "a", encoding="utf-8") if log_path is not None else None  # noqa: SIM115

    try:
        process = subprocess.Popen(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, bufsize=1
        )
    except FileNotFoundError as exc:
        if log_file is not None:
            log_file.close()
        raise RuntimeError(
            "cloudflared is not installed or not on PATH — install it separately "
            "(https://developers.cloudflare.com/cloudflare-one/connections/connect-networks"
            "/downloads/); this repo only shells out to it, it is not a Python dependency"
        ) from exc

    line_queue: queue.Queue[str] = queue.Queue()
    threading.Thread(target=_stream_lines, args=(process.stderr, line_queue), daemon=True).start()

    deadline = time.monotonic() + timeout_seconds
    captured: list[str] = []
    while time.monotonic() < deadline:
        if process.poll() is not None:
            if log_file is not None:
                log_file.close()
            raise RuntimeError(
                f"cloudflared exited before reporting a tunnel URL (exit code "
                f"{process.returncode}) — captured output:\n{''.join(captured)}"
            )
        try:
            line = line_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        captured.append(line)
        if log_file is not None:
            log_file.write(line)
            log_file.flush()
        match = _URL_PATTERN.search(line)
        if match is not None:
            return Tunnel(process=process, public_url=match.group(0), log_file=log_file)

    process.terminate()
    if log_file is not None:
        log_file.close()
    raise TimeoutError(f"cloudflared never reported a *.trycloudflare.com URL within {timeout_seconds}s")
