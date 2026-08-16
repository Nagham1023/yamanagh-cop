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
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from cop.tools.tunnel import _ngrok_command, stop_tunnel
from cop.tools.tunnel_start import start_tunnel

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


def test_ngrok_command_without_a_domain_is_the_original_bare_form():
    assert _ngrok_command(8000, None) == ["ngrok", "http", "8000"]


def test_ngrok_command_with_a_domain_inserts_the_domain_flag_before_the_port():
    assert _ngrok_command(8000, "my-name.ngrok-free.app") == [
        "ngrok", "http", "--domain=my-name.ngrok-free.app", "8000",
    ]


def test_start_tunnel_uses_the_domain_flag_when_no_explicit_command_is_given(monkeypatch):
    # Proves start_tunnel actually wires `domain` into what it launches,
    # without needing the real ngrok binary installed — same substitution
    # shape the other tests use for subprocess.Popen itself, just one
    # layer up (the constructed command, not the process launch).
    # `admin_api_url` pointed at a guaranteed-empty port, not the real
    # default — a genuine ngrok agent legitimately running on this same
    # machine for an actual match must not make this test see the
    # "already answering" refusal instead of the Popen failure it means
    # to prove.
    import cop.tools.tunnel as tunnel_module

    captured = {}

    def _fake_popen(command, **kwargs):
        captured["command"] = command
        raise FileNotFoundError("stand-in: never actually launches anything")

    monkeypatch.setattr(tunnel_module.subprocess, "Popen", _fake_popen)

    with pytest.raises(RuntimeError, match="ngrok is not installed"):
        start_tunnel(
            8000, admin_api_url="http://127.0.0.1:1/api/tunnels", domain="my-name.ngrok-free.app"
        )

    assert captured["command"] == ["ngrok", "http", "--domain=my-name.ngrok-free.app", "8000"]


def test_start_tunnel_an_explicit_command_wins_over_domain():
    # domain is silently ignored when command is given explicitly -- the
    # explicit command is exactly what test infrastructure everywhere else
    # in this file already relies on taking precedence.
    admin_api_url, server = _admin_api_stub(
        {"tunnels": [{"proto": "https", "public_url": "https://abc123.ngrok-free.app"}]}
    )
    try:
        tunnel = start_tunnel(
            8000, admin_api_url=admin_api_url, command=_PLACEHOLDER_COMMAND, domain="ignored.example.com"
        )
        assert tunnel.public_url == "https://abc123.ngrok-free.app"
        stop_tunnel(tunnel)
    finally:
        server.shutdown()


def test_start_tunnel_raises_a_clear_error_when_ngrok_is_not_on_path(monkeypatch):
    # Simulated via subprocess.Popen, not real absence: TODO5 §0 originally
    # relied on ngrok genuinely not being installed in this dev environment,
    # but that stopped holding once ngrok was installed for real tunnel
    # testing (PRD 5) — at which point this test, unguarded, actually
    # launched a real, un-terminated `ngrok` process on every run (found
    # live: a leaked `ngrok http 8000` still holding port 4040 well after
    # the test suite finished). Same substitution shape as
    # `test_start_tunnel_uses_the_domain_flag_when_no_explicit_command_is_given`
    # just above — proves the *error handling*, independent of whether
    # ngrok happens to be present on whatever machine runs this.
    # `admin_api_url` pointed at a guaranteed-empty port, not the real
    # default, for the same "don't collide with a real concurrent match"
    # reason as that sibling test.
    import cop.tools.tunnel as tunnel_module

    def _fake_popen(command, **kwargs):
        raise FileNotFoundError("stand-in: never actually launches anything")

    monkeypatch.setattr(tunnel_module.subprocess, "Popen", _fake_popen)

    with pytest.raises(RuntimeError, match="ngrok is not installed"):
        start_tunnel(8000, admin_api_url="http://127.0.0.1:1/api/tunnels")


def test_start_tunnel_raises_clearly_when_ngrok_exits_before_reporting_a_tunnel(tmp_path):
    # The real bug this closes: ngrok can exit near-instantly with its own
    # error (ERR_NGROK_334 — "endpoint already online", found live when an
    # hours-old orphaned ngrok process was still squatting on the reserved
    # domain) while the admin API poll alone has no way to distinguish
    # "no tunnel yet" from "this is a stale tunnel belonging to a
    # different process" — only noticing the process's own exit catches
    # this. No admin API stub needed: the process exits before ever
    # reaching that poll.
    admin_api_url = "http://127.0.0.1:1/api/tunnels"  # nothing listens on port 1
    log_path = tmp_path / "ngrok.log"
    dying_command = [
        sys.executable, "-c",
        "print('ERROR:  ERR_NGROK_334', flush=True); import sys; sys.exit(1)",
    ]

    with pytest.raises(RuntimeError, match="exited before reporting a tunnel"):
        start_tunnel(
            8000, admin_api_url=admin_api_url, command=dying_command, log_path=str(log_path)
        )


def test_start_tunnel_refuses_to_launch_when_another_agent_already_answers_the_admin_api():
    # The real bug this closes: an hours-old orphaned ngrok agent was
    # still answering the admin API when a later real launch's own
    # subprocess failed instantly (ERR_NGROK_334, "already online") — the
    # polling loop found the *old* agent's still-valid tunnel info before
    # ever noticing this invocation's own subprocess had died, silently
    # declaring success using someone else's stale tunnel. Refusing
    # up front, before ever spawning anything, closes that gap for real.
    admin_api_url, server = _admin_api_stub(
        {"tunnels": [{"proto": "https", "public_url": "https://someone-elses-tunnel.ngrok-free.app"}]}
    )
    popen_calls = []
    try:
        import cop.tools.tunnel_start as tunnel_start_module

        def _fake_popen(*args, **kwargs):
            popen_calls.append(args)
            raise AssertionError("must not even try to launch a second ngrok agent")

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(tunnel_start_module.subprocess, "Popen", _fake_popen)
            with pytest.raises(RuntimeError, match="already answering"):
                start_tunnel(8000, admin_api_url=admin_api_url)  # command=None -> the real launch path

        assert popen_calls == []
    finally:
        server.shutdown()


def test_start_tunnel_times_out_when_the_admin_api_never_reports_a_tunnel():
    admin_api_url, server = _admin_api_stub({"tunnels": []})
    try:
        with pytest.raises(TimeoutError):
            start_tunnel(
                8000, admin_api_url=admin_api_url, timeout_seconds=0.5, command=_PLACEHOLDER_COMMAND
            )
    finally:
        server.shutdown()


def test_start_tunnel_with_a_log_path_captures_the_process_own_stdout(tmp_path):
    # The real diagnostic gap this closes: ngrok's own connection
    # errors/rate-limit rejections used to be discarded (`DEVNULL`),
    # invisible even when a real match's failure was happening at the
    # tunnel level rather than in this repo's own code.
    admin_api_url, server = _admin_api_stub(
        {"tunnels": [{"proto": "https", "public_url": "https://abc123.ngrok-free.app"}]}
    )
    log_path = tmp_path / "ngrok.log"
    talking_command = [
        sys.executable, "-c",
        "print('hello from ngrok stand-in', flush=True); import time; time.sleep(60)",
    ]
    try:
        tunnel = start_tunnel(
            8000, admin_api_url=admin_api_url, command=talking_command, log_path=str(log_path)
        )
        time.sleep(0.3)  # let the subprocess actually flush its print
        stop_tunnel(tunnel)
        assert "hello from ngrok stand-in" in log_path.read_text(encoding="utf-8")
    finally:
        server.shutdown()


def test_start_tunnel_without_a_log_path_keeps_the_old_silent_devnull_behavior():
    admin_api_url, server = _admin_api_stub(
        {"tunnels": [{"proto": "https", "public_url": "https://abc123.ngrok-free.app"}]}
    )
    try:
        tunnel = start_tunnel(8000, admin_api_url=admin_api_url, command=_PLACEHOLDER_COMMAND)
        assert tunnel.log_file is None
        stop_tunnel(tunnel)  # must not raise even with nothing to close
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
