"""cli_peer.py::run_peer's std_v1 dispatch branch — `[network]
opponent_protocol = "std_v1"` must short-circuit straight to
`run_std_v1_peer`, never building a native `Orchestrator` at all. A
monkeypatched `run_std_v1_peer` keeps this test isolated from a real
network match, unlike `test_cli_peer.py`'s own real two-process tests.
"""

from __future__ import annotations

import asyncio

import cop.cli_peer as cli_peer


def _write_private_config(tmp_path, **network_overrides) -> str:
    path = tmp_path / "game.toml"
    network = {"my_port": 8801, "opponent_url": "http://127.0.0.1:8802/mcp", "turn_timeout_seconds": 30}
    network.update(network_overrides)
    network_lines = "\n".join(
        f'{key} = {value!r}' if isinstance(value, str) else f"{key} = {value}"
        for key, value in network.items()
    )
    path.write_text(
        f"""
[game]
group_name = "dev-team"
group_id = "dev-team"
sub_game_number = 1
members = ["dev-1"]
repos = {{ cop = "https://x/cop", thief = "https://x/thief" }}

[network]
{network_lines}

[trash_talk]
provider = "template"
every_n_steps = 1

[llm]
model = "claude-sonnet-5"
step_deadline_seconds = 30

[email]
recipient = "x@y.com"
mode = "draft"
""",
        encoding="utf-8",
    )
    return str(path)


def test_run_peer_dispatches_to_std_v1_when_configured(tmp_path, monkeypatch):
    private_config_path = _write_private_config(
        tmp_path, opponent_protocol="std_v1", opponent_group_id="thief-team"
    )
    captured = {}

    async def _fake_run_std_v1_peer(private_config, base_config, *, use_tunnel=False, ngrok_domain=None):
        captured["private_config"] = private_config
        captured["base_config"] = base_config
        return {"agreed": True}

    monkeypatch.setattr(cli_peer, "run_std_v1_peer", _fake_run_std_v1_peer)

    result = asyncio.run(cli_peer.run_peer(
        private_config_path=private_config_path,
        shared_config_path="config/shared/config_dev_g01.json",
    ))

    assert result == {"agreed": True}
    assert captured["private_config"].opponent_protocol == "std_v1"
    assert captured["private_config"].opponent_group_id == "thief-team"


def test_run_peer_does_not_dispatch_to_std_v1_by_default(tmp_path, monkeypatch):
    private_config_path = _write_private_config(tmp_path)
    called = []
    monkeypatch.setattr(
        cli_peer, "run_std_v1_peer", lambda *a, **k: called.append(True)
    )

    async def _fake_run_match_body(*args, **kwargs):
        return "native-result"

    monkeypatch.setattr(cli_peer, "run_match_body", _fake_run_match_body)

    result = asyncio.run(cli_peer.run_peer(
        private_config_path=private_config_path,
        shared_config_path="config/shared/config_dev_g01.json",
    ))

    assert called == []
    assert result == "native-result"
