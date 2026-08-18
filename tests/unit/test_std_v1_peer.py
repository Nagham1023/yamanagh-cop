"""std_v1/peer.py::run_std_v1_peer -- the tunnel-URL wiring into the
declared `identity.mcp_servers`, and rule 52's own `LeagueLedger` wiring
(`counted`/`league_ledger_path` -- std_v1 used to never touch the ledger
at all). `start_tunnel`/`play_series` are monkeypatched so this stays
isolated from a real network match; the real FastMCP server thread and
`PeerConnection` still run for real, same as every other
`run_as_server`-adjacent test in this repo.
"""

from __future__ import annotations

import asyncio
import socket

import pytest

import cop.std_v1.peer as peer_module
from cop.policy.league_ledger import LeagueLedger
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


def test_run_std_v1_peer_uses_cloudflare_when_asked_not_hardcoded_ngrok(config, monkeypatch, tmp_path):
    # The real bug this closes: --tunnel-provider cloudflare was silently
    # ignored here -- run_std_v1_peer always called ngrok's own
    # start_tunnel regardless, found live starting a real match.
    captured = {}

    def _fake_start_cloudflare_tunnel(port, log_path=None):
        captured["cloudflare_called"] = True
        return Tunnel(process=None, public_url="https://fake.trycloudflare.com", log_file=None)

    def _fake_start_tunnel(port, domain=None, log_path=None):
        captured["ngrok_called"] = True
        return Tunnel(process=None, public_url="https://fake-tunnel.example.com", log_file=None)

    async def _fake_play_series(connection, exchange, terms, my_group_id, their_group_id, identity, *a, **kw):
        return {"report": {"game_id": "x"}, "game_id": "x"}

    monkeypatch.setattr(peer_module, "start_cloudflare_tunnel", _fake_start_cloudflare_tunnel)
    monkeypatch.setattr(peer_module, "start_tunnel", _fake_start_tunnel)
    monkeypatch.setattr(peer_module, "play_series", _fake_play_series)
    monkeypatch.setattr(peer_module, "stop_tunnel", lambda tunnel: None)

    asyncio.run(peer_module.run_std_v1_peer(
        _private_config(), config, use_tunnel=True, tunnel_provider="cloudflare", results_dir=str(tmp_path),
    ))

    assert captured.get("cloudflare_called") is True
    assert "ngrok_called" not in captured


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


async def _fake_play_series_success(connection, exchange, terms, my_group_id, their_group_id, identity, *a, **kw):
    return {"report": {"game_id": "x"}, "game_id": "x"}


def test_run_std_v1_peer_records_a_counted_game_in_the_league_ledger(config, monkeypatch, tmp_path):
    private_config = _private_config()
    ledger_path = str(tmp_path / "ledger.json")
    monkeypatch.setattr(peer_module, "play_series", _fake_play_series_success)

    asyncio.run(peer_module.run_std_v1_peer(
        private_config, config, use_tunnel=False, results_dir=str(tmp_path),
        counted=True, league_ledger_path=ledger_path,
    ))

    ledger = LeagueLedger(path=ledger_path)
    assert ledger.is_already_counted(private_config.opponent_url) is True
    assert ledger.counted_game_count() == 1


def test_run_std_v1_peer_does_not_touch_the_ledger_when_uncounted(config, monkeypatch, tmp_path):
    private_config = _private_config()
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(peer_module, "play_series", _fake_play_series_success)

    asyncio.run(peer_module.run_std_v1_peer(
        private_config, config, use_tunnel=False, results_dir=str(tmp_path),
        league_ledger_path=str(ledger_path),
    ))

    # Warm-ups (counted defaulting to False) are never recorded at all --
    # league_ledger.py's own documented invariant, matching native.
    assert ledger_path.exists() is False


def test_run_std_v1_peer_uses_the_default_ledger_path_when_none_is_given(config, monkeypatch, tmp_path):
    private_config = _private_config()
    monkeypatch.setattr(peer_module, "play_series", _fake_play_series_success)
    captured = {}

    class _SpyLedger:
        def __init__(self, path=None):
            captured["path"] = path

        def record_counted_game(self, opponent_id):
            captured["opponent_id"] = opponent_id

    monkeypatch.setattr(peer_module, "LeagueLedger", _SpyLedger)

    asyncio.run(peer_module.run_std_v1_peer(
        private_config, config, use_tunnel=False, results_dir=str(tmp_path), counted=True,
    ))

    # No league_ledger_path given -> constructed with no path kwarg at all,
    # so LeagueLedger's own default (logs/league_ledger.json) applies --
    # the same default Orchestrator/cli_peer_build.py itself relies on.
    assert captured["path"] is None
    assert captured["opponent_id"] == private_config.opponent_url


def test_run_std_v1_peer_rejects_a_second_counted_game_against_the_same_opponent(config, monkeypatch, tmp_path):
    ledger_path = str(tmp_path / "ledger.json")
    monkeypatch.setattr(peer_module, "play_series", _fake_play_series_success)

    private_config_a = _private_config(my_port=_free_port())
    asyncio.run(peer_module.run_std_v1_peer(
        private_config_a, config, use_tunnel=False, results_dir=str(tmp_path),
        counted=True, league_ledger_path=ledger_path,
    ))
    first_result_path = tmp_path / "result_x.json"  # _fake_play_series_success's own game_id
    assert first_result_path.exists()  # game 1's own artifacts really were written

    private_config_b = _private_config(my_port=_free_port())
    with pytest.raises(ValueError, match="rule 52"):
        asyncio.run(peer_module.run_std_v1_peer(
            private_config_b, config, use_tunnel=False, results_dir=str(tmp_path),
            counted=True, league_ledger_path=ledger_path,
        ))

    # The rejection on game 2 must not retroactively touch game 1's data.
    assert first_result_path.exists()
