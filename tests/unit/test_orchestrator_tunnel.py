"""Orchestrator.run_as_server's tunnel wiring and host-binding resolution
(PRD 5) — split out to keep test_orchestrator.py focused on the client
role. No real `ngrok` binary needed: `start_tunnel`'s `admin_api_url`/
`command` parameters (tools/tunnel.py) let every test here point at a
local stand-in, same discipline as test_tunnel.py itself. `self.server.run`
is stubbed to a no-op so `run_as_server` completes synchronously — no
background thread, no sleep, and the tunnel's `finally`-block teardown
(`stop_tunnel`) is directly observable in the same test.
"""

from __future__ import annotations

import json
import socket
import sys

from test_tunnel import _admin_api_stub

import cop.orchestrator_server as server_module
from cop.orchestrator import Orchestrator
from cop.reasoning.cop_brain import CopBrain
from cop.tools.tunnel_start import start_tunnel as real_start_tunnel

_PLACEHOLDER_COMMAND = [sys.executable, "-c", "import time; time.sleep(60)"]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _events(tmp_path) -> list[dict]:
    return [
        json.loads(line)
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def test_run_as_server_with_use_tunnel_starts_and_stops_the_tunnel(config, tmp_path, monkeypatch):
    admin_api_url, admin_server = _admin_api_stub(
        {"tunnels": [{"proto": "https", "public_url": "https://abc123.ngrok-free.app"}]}
    )
    started = {}

    def _fake_start_tunnel(port, domain=None, log_path=None):
        tunnel = real_start_tunnel(
            port, admin_api_url=admin_api_url, command=_PLACEHOLDER_COMMAND, domain=domain
        )
        started["tunnel"] = tunnel
        return tunnel

    monkeypatch.setattr(server_module, "start_tunnel", _fake_start_tunnel)

    try:
        orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
        monkeypatch.setattr(orchestrator.server, "run", lambda **kwargs: None)

        orchestrator.run_as_server(port=_free_port(), use_tunnel=True)

        events = _events(tmp_path)
        (tunnel_event,) = [e for e in events if e["event"] == "tunnel_started"]
        assert tunnel_event["public_url"] == "https://abc123.ngrok-free.app"
        (server_event,) = [e for e in events if e["event"] == "server_starting"]
        assert server_event["host"] == "0.0.0.0"
        assert started["tunnel"].process.poll() is not None, "stop_tunnel must terminate the process"
    finally:
        admin_server.shutdown()


def test_run_as_server_without_use_tunnel_binds_127_0_0_1_and_starts_no_tunnel(config, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(server_module, "start_tunnel", lambda port, domain=None, log_path=None: calls.append(port))

    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    monkeypatch.setattr(orchestrator.server, "run", lambda **kwargs: None)

    orchestrator.run_as_server(port=_free_port())

    assert calls == []
    events = _events(tmp_path)
    (server_event,) = [e for e in events if e["event"] == "server_starting"]
    assert server_event["host"] == "127.0.0.1"
    assert not [e for e in events if e["event"] == "tunnel_started"]


def test_run_as_server_an_explicit_host_wins_over_the_use_tunnel_default(config, tmp_path, monkeypatch):
    # use_tunnel=True would normally resolve host to "0.0.0.0" — an
    # explicit host must still win over that default, even though tunnel
    # *starting* itself is still governed by use_tunnel independently.
    admin_api_url, admin_server = _admin_api_stub(
        {"tunnels": [{"proto": "https", "public_url": "https://abc123.ngrok-free.app"}]}
    )
    monkeypatch.setattr(
        server_module,
        "start_tunnel",
        lambda port, domain=None, log_path=None: real_start_tunnel(
            port, admin_api_url=admin_api_url, command=_PLACEHOLDER_COMMAND, domain=domain
        ),
    )

    try:
        orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
        monkeypatch.setattr(orchestrator.server, "run", lambda **kwargs: None)

        orchestrator.run_as_server(host="192.168.1.50", port=_free_port(), use_tunnel=True)

        events = _events(tmp_path)
        (server_event,) = [e for e in events if e["event"] == "server_starting"]
        assert server_event["host"] == "192.168.1.50"
        assert [e for e in events if e["event"] == "tunnel_started"]  # still started
    finally:
        admin_server.shutdown()


def test_run_as_server_threads_ngrok_domain_through_to_start_tunnel(config, tmp_path, monkeypatch):
    admin_api_url, admin_server = _admin_api_stub(
        {"tunnels": [{"proto": "https", "public_url": "https://my-name.ngrok-free.app"}]}
    )
    received = {}

    def _fake_start_tunnel(port, domain=None, log_path=None):
        received["domain"] = domain
        return real_start_tunnel(
            port, admin_api_url=admin_api_url, command=_PLACEHOLDER_COMMAND, domain=domain
        )

    monkeypatch.setattr(server_module, "start_tunnel", _fake_start_tunnel)

    try:
        orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
        monkeypatch.setattr(orchestrator.server, "run", lambda **kwargs: None)

        orchestrator.run_as_server(port=_free_port(), use_tunnel=True, ngrok_domain="my-name.ngrok-free.app")

        assert received["domain"] == "my-name.ngrok-free.app"
    finally:
        admin_server.shutdown()
