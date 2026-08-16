"""tools/cloudflare_tunnel.py: parses a real `cloudflared` stderr shape
against a placeholder subprocess — same "prove the parsing logic without
needing the real binary in every dev/CI environment" discipline
`test_tunnel.py` already uses for ngrok, adapted for stderr-line polling
instead of an admin-API poll (`cloudflared` has no equivalent API for a
Quick Tunnel). The real `cloudflared` binary was used once, live, to
confirm the exact stderr shape these placeholder commands reproduce.
"""

from __future__ import annotations

import sys
import time

import pytest

from cop.tools.cloudflare_tunnel import _cloudflared_command, start_cloudflare_tunnel
from cop.tools.tunnel import stop_tunnel

_SLEEP_ONLY_COMMAND = [sys.executable, "-c", "import time; time.sleep(60)"]


def _stderr_command(*lines: str) -> list[str]:
    """A placeholder process that prints each line to stderr (flushed),
    then sleeps — reproducing `cloudflared`'s own real behavior of writing
    everything, including the assigned URL, to stderr rather than stdout."""
    body = "; ".join(f"print({line!r}, file=__import__('sys').stderr, flush=True)" for line in lines)
    return [sys.executable, "-c", f"{body}; import time; time.sleep(60)"]


def test_cloudflared_command_shape():
    assert _cloudflared_command(8000) == [
        "cloudflared", "tunnel", "--url", "http://localhost:8000", "--loglevel", "info",
    ]


def test_start_cloudflare_tunnel_parses_the_url_from_a_real_shaped_stderr_line():
    command = _stderr_command(
        "2026-01-01T00:00:00Z INF |  https://puts-items-rarely-thousands.trycloudflare.com  |"
    )
    tunnel = start_cloudflare_tunnel(8000, command=command)
    try:
        assert tunnel.public_url == "https://puts-items-rarely-thousands.trycloudflare.com"
    finally:
        stop_tunnel(tunnel)


def test_start_cloudflare_tunnel_skips_preamble_lines_before_the_url():
    # The real binary prints ~10 lines of terms-of-service/version/settings
    # noise before ever reaching the URL — the polling loop must keep
    # reading past all of it, not just check the first line.
    command = _stderr_command(
        "2026-01-01T00:00:00Z INF Thank you for trying Cloudflare Tunnel.",
        "2026-01-01T00:00:00Z INF Requesting new quick Tunnel on trycloudflare.com...",
        "2026-01-01T00:00:00Z INF +----------------------------------------+",
        "2026-01-01T00:00:00Z INF |  https://abc-def-ghi.trycloudflare.com  |",
    )
    tunnel = start_cloudflare_tunnel(8000, command=command)
    try:
        assert tunnel.public_url == "https://abc-def-ghi.trycloudflare.com"
    finally:
        stop_tunnel(tunnel)


def test_start_cloudflare_tunnel_raises_when_cloudflared_exits_before_reporting_a_url():
    dying_command = [
        sys.executable, "-c",
        "import sys; print('some fatal error', file=sys.stderr, flush=True); sys.exit(1)",
    ]
    with pytest.raises(RuntimeError, match="exited before reporting a tunnel URL"):
        start_cloudflare_tunnel(8000, command=dying_command)


def test_start_cloudflare_tunnel_times_out_when_no_url_ever_appears():
    with pytest.raises(TimeoutError):
        start_cloudflare_tunnel(8000, timeout_seconds=0.5, command=_SLEEP_ONLY_COMMAND)


def test_start_cloudflare_tunnel_raises_a_clear_error_when_cloudflared_is_not_on_path(monkeypatch):
    import cop.tools.cloudflare_tunnel as cf_module

    def _fake_popen(command, **kwargs):
        raise FileNotFoundError("stand-in: never actually launches anything")

    monkeypatch.setattr(cf_module.subprocess, "Popen", _fake_popen)

    with pytest.raises(RuntimeError, match="cloudflared is not installed"):
        start_cloudflare_tunnel(8000)


def test_start_cloudflare_tunnel_with_a_log_path_captures_the_process_own_stderr(tmp_path):
    log_path = tmp_path / "cloudflared.log"
    command = _stderr_command(
        "hello from cloudflared stand-in",
        "https://abc-def-ghi.trycloudflare.com",
    )
    tunnel = start_cloudflare_tunnel(8000, command=command, log_path=str(log_path))
    try:
        time.sleep(0.2)  # let the subprocess actually flush
        assert "hello from cloudflared stand-in" in log_path.read_text(encoding="utf-8")
    finally:
        stop_tunnel(tunnel)


def test_start_cloudflare_tunnel_without_a_log_path_keeps_log_file_none():
    command = _stderr_command("https://abc-def-ghi.trycloudflare.com")
    tunnel = start_cloudflare_tunnel(8000, command=command)
    try:
        assert tunnel.log_file is None
    finally:
        stop_tunnel(tunnel)  # must not raise even with nothing to close
