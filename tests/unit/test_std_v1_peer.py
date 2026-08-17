"""std_v1/peer.py::run_std_v1_peer -- specifically the tunnel-URL wiring
into the declared `identity.mcp_servers`. `start_tunnel`/`play_series`
are monkeypatched so this stays isolated from a real network match; the
real FastMCP server thread and `PeerConnection` still run for real, same
as every other `run_as_server`-adjacent test in this repo.
"""

from __future__ import annotations

import asyncio
import socket

import cop.std_v1.peer as peer_module
from cop.shared.private_config import PrivateConfig
from cop.tools.tunnel import Tunnel


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _private_config(**overrides) -> PrivateConfig:
    base = {
        "provider": "template", "every_n_steps": 1, "opponent_url": "http://127.0.0.1:1/mcp",
        "my_port": _free_port(), "turn_timeout_seconds": 30.0, "initiate_step0": False,
        "step0_wait_seconds": 300.0, "scent_map_retry_attempts": 3, "scent_map_retry_delay_seconds": 1.0,
        "post_match_grace_seconds": 60.0, "group_name": "dev-team", "group_id": "dev-team",
        "sub_game_number": 1, "members": ("dev-1",), "repos": {}, "model": "claude-sonnet-5",
        "step_deadline_seconds": 30.0, "email_recipient": "x@y.com", "email_mode": "draft",
        "opponent_protocol": "std_v1", "opponent_group_id": "thief-team",
    }
    base.update(overrides)
    return PrivateConfig(**base)


def test_run_std_v1_peer_declares_the_real_tunnel_url_not_localhost(config, monkeypatch, tmp_path):
    # The real bug this closes: mcp_servers used to be hardcoded to
    # 127.0.0.1 even when a real public tunnel was up -- the exact
    # address recorded in our own report and sent to the opponent as our
    # reachable endpoint (spec Section 3/12 [REPORT]) would be useless to
    # anyone outside this machine.
    captured = {}

    def _fake_start_tunnel(port, domain=None, log_path=None):
        return Tunnel(process=None, public_url="https://fake-tunnel.example.com", log_file=None)

    async def _fake_play_series(connection, exchange, terms, my_group_id, their_group_id, identity, *a, **kw):
        captured["identity"] = identity
        return {"report": {"game_id": "x"}, "game_id": "x"}

    monkeypatch.setattr(peer_module, "start_tunnel", _fake_start_tunnel)
    monkeypatch.setattr(peer_module, "play_series", _fake_play_series)
    monkeypatch.setattr(peer_module, "stop_tunnel", lambda tunnel: None)

    asyncio.run(
        peer_module.run_std_v1_peer(_private_config(), config, use_tunnel=True, results_dir=str(tmp_path))
    )

    assert captured["identity"]["mcp_servers"] == {
        "cop": "https://fake-tunnel.example.com/mcp",
        "thief": "https://fake-tunnel.example.com/mcp",
    }


def test_run_std_v1_peer_threads_real_private_config_values_into_play_series(config, monkeypatch, tmp_path):
    # I6: negotiate_ceiling_sec/audit_ceiling_sec/resend_interval_sec/
    # retry_attempts/retry_delay_seconds used to default to fixed literals
    # at every real call -- must now come from PrivateConfig, not a copy
    # of the same numbers baked in twice.
    captured = {}
    private_config = _private_config(
        step0_wait_seconds=123.0, post_match_grace_seconds=45.0,
        scent_map_retry_attempts=7, scent_map_retry_delay_seconds=2.5,
    )

    async def _fake_play_series(connection, exchange, terms, my_group_id, their_group_id, identity, *a, **kw):
        captured.update(kw)
        return {"report": {"game_id": "x"}, "game_id": "x"}

    monkeypatch.setattr(peer_module, "play_series", _fake_play_series)

    asyncio.run(
        peer_module.run_std_v1_peer(private_config, config, use_tunnel=False, results_dir=str(tmp_path))
    )

    assert captured["negotiate_ceiling_sec"] == 123.0
    assert captured["audit_ceiling_sec"] == 45.0
    assert captured["resend_interval_sec"] == 2.5
    assert captured["retry_attempts"] == 7
    assert captured["retry_delay_seconds"] == 2.5


def test_run_std_v1_peer_uses_localhost_when_not_tunneled(config, monkeypatch, tmp_path):
    captured = {}
    private_config = _private_config()

    async def _fake_play_series(connection, exchange, terms, my_group_id, their_group_id, identity, *a, **kw):
        captured["identity"] = identity
        return {"report": {"game_id": "x"}, "game_id": "x"}

    monkeypatch.setattr(peer_module, "play_series", _fake_play_series)

    asyncio.run(
        peer_module.run_std_v1_peer(private_config, config, use_tunnel=False, results_dir=str(tmp_path))
    )

    port = private_config.my_port
    assert captured["identity"]["mcp_servers"] == {
        "cop": f"http://127.0.0.1:{port}/mcp",
        "thief": f"http://127.0.0.1:{port}/mcp",
    }
