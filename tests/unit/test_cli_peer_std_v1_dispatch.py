"""cli_peer.py's std_v1 wiring — `[network] opponent_protocol = "std_v1"`
must short-circuit `run_peer` straight to `run_std_v1_peer`, never building
a native `Orchestrator` at all, and `counted`/`league_ledger_path` must
thread through to it rather than being dropped (the std_v1 side of rule
52's enforcement). `run_peer_with_gui` must instead *reject* the
combination outright — std_v1 has no GUI anywhere in its own package, a
permanent scope limit, so silently falling through to a native match would
run the wrong protocol with no error. A monkeypatched `run_std_v1_peer`/
`play_series` keeps most of this isolated from a real network match,
unlike `test_cli_peer.py`'s own real two-process tests.
"""

from __future__ import annotations

import asyncio
import socket

import pytest

import cop.cli_peer as cli_peer


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _write_private_config(tmp_path, filename="game.toml", **network_overrides) -> str:
    path = tmp_path / filename
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

    async def _fake_run_std_v1_peer(
        private_config, base_config, *, use_tunnel=False, ngrok_domain=None, sub_games_to_play=None,
        counted=False, league_ledger_path=None,
    ):
        captured["private_config"] = private_config
        captured["base_config"] = base_config
        captured["sub_games_to_play"] = sub_games_to_play
        return {"agreed": True}

    monkeypatch.setattr(cli_peer, "run_std_v1_peer", _fake_run_std_v1_peer)

    result = asyncio.run(cli_peer.run_peer(
        private_config_path=private_config_path,
        shared_config_path="config/shared/config_dev_g01.json",
    ))

    assert result == {"agreed": True}
    assert captured["private_config"].opponent_protocol == "std_v1"
    assert captured["private_config"].opponent_group_id == "thief-team"
    assert captured["sub_games_to_play"] is None  # default: play the full signed series


def test_run_peer_threads_std_v1_sub_games_through_to_run_std_v1_peer(tmp_path, monkeypatch):
    # Spec Section 15's own compatibility-test launch parameter — must
    # reach run_std_v1_peer unchanged, never silently dropped.
    private_config_path = _write_private_config(
        tmp_path, opponent_protocol="std_v1", opponent_group_id="thief-team"
    )
    captured = {}

    async def _fake_run_std_v1_peer(
        private_config, base_config, *, use_tunnel=False, ngrok_domain=None, sub_games_to_play=None,
        counted=False, league_ledger_path=None,
    ):
        captured["sub_games_to_play"] = sub_games_to_play
        return {"agreed": True}

    monkeypatch.setattr(cli_peer, "run_std_v1_peer", _fake_run_std_v1_peer)

    asyncio.run(cli_peer.run_peer(
        private_config_path=private_config_path,
        shared_config_path="config/shared/config_dev_g01.json",
        std_v1_sub_games=2,
    ))

    assert captured["sub_games_to_play"] == 2


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


def test_run_peer_threads_counted_and_league_ledger_path_through_to_run_std_v1_peer(tmp_path, monkeypatch):
    # counted/league_ledger_path used to be dropped entirely on this branch
    # -- a real rule-52 enforcement gap, not a cosmetic one.
    private_config_path = _write_private_config(
        tmp_path, opponent_protocol="std_v1", opponent_group_id="thief-team"
    )
    captured = {}

    async def _fake_run_std_v1_peer(
        private_config, base_config, *, use_tunnel=False, ngrok_domain=None,
        sub_games_to_play=None, counted=False, league_ledger_path=None,
    ):
        captured["counted"] = counted
        captured["league_ledger_path"] = league_ledger_path
        return {"agreed": True}

    monkeypatch.setattr(cli_peer, "run_std_v1_peer", _fake_run_std_v1_peer)

    asyncio.run(cli_peer.run_peer(
        private_config_path=private_config_path,
        shared_config_path="config/shared/config_dev_g01.json",
        counted=True,
        league_ledger_path="some/path.json",
    ))

    assert captured["counted"] is True
    assert captured["league_ledger_path"] == "some/path.json"


def test_run_peer_defaults_counted_false_and_league_ledger_path_none_for_std_v1_too(tmp_path, monkeypatch):
    private_config_path = _write_private_config(
        tmp_path, opponent_protocol="std_v1", opponent_group_id="thief-team"
    )
    captured = {}

    async def _fake_run_std_v1_peer(
        private_config, base_config, *, use_tunnel=False, ngrok_domain=None,
        sub_games_to_play=None, counted=False, league_ledger_path=None,
    ):
        captured["counted"] = counted
        captured["league_ledger_path"] = league_ledger_path
        return {"agreed": True}

    monkeypatch.setattr(cli_peer, "run_std_v1_peer", _fake_run_std_v1_peer)

    asyncio.run(cli_peer.run_peer(
        private_config_path=private_config_path,
        shared_config_path="config/shared/config_dev_g01.json",
    ))

    assert captured["counted"] is False
    assert captured["league_ledger_path"] is None


def test_run_peer_propagates_a_std_v1_rule_52_violation_end_to_end(tmp_path, monkeypatch):
    # Drives the REAL dispatch branch (not a monkeypatched run_std_v1_peer)
    # so this proves the whole chain -- run_peer -> run_std_v1_peer ->
    # LeagueLedger -- is wired end to end, not just at the leaf function.
    # Two distinct configs (distinct my_port, so each gets its own real
    # FastMCP server thread with no bind conflict) but the SAME
    # opponent_url -- that shared value is the ledger key rule 52 checks.
    import cop.std_v1.peer as peer_module

    shared_opponent_url = "http://127.0.0.1:8802/mcp"
    config_a = _write_private_config(
        tmp_path, filename="game_a.toml", my_port=_free_port(),
        opponent_url=shared_opponent_url, opponent_protocol="std_v1", opponent_group_id="thief-team",
    )
    config_b = _write_private_config(
        tmp_path, filename="game_b.toml", my_port=_free_port(),
        opponent_url=shared_opponent_url, opponent_protocol="std_v1", opponent_group_id="thief-team",
    )
    ledger_path = str(tmp_path / "ledger.json")

    async def _fake_play_series(connection, exchange, terms, my_group_id, their_group_id, identity, *a, **kw):
        return {"report": {"game_id": "x"}, "game_id": "x"}

    monkeypatch.setattr(peer_module, "play_series", _fake_play_series)
    # No-op the result-file writers rather than chdir()ing the whole
    # process -- run_peer's std_v1 branch doesn't expose results_dir, and
    # DEFAULT_TERMS_PATH ("config/interop_spec_terms.json") is resolved
    # relative to cwd, so chdir()ing here would break that real read.
    monkeypatch.setattr(peer_module, "write_std_v1_result", lambda result, results_dir: None)
    monkeypatch.setattr(peer_module, "write_std_v1_sub_game_logs", lambda result, results_dir: [])

    async def _run() -> None:
        await cli_peer.run_peer(
            private_config_path=config_a,
            shared_config_path="config/shared/config_dev_g01.json",
            counted=True,
            league_ledger_path=ledger_path,
        )
        await cli_peer.run_peer(
            private_config_path=config_b,
            shared_config_path="config/shared/config_dev_g01.json",
            counted=True,
            league_ledger_path=ledger_path,
        )

    with pytest.raises(ValueError, match="rule 52"):
        asyncio.run(_run())


def test_run_peer_with_gui_rejects_std_v1_before_building_any_native_orchestrator(tmp_path, monkeypatch):
    private_config_path = _write_private_config(
        tmp_path, opponent_protocol="std_v1", opponent_group_id="thief-team"
    )

    def _should_not_be_called(*args, **kwargs):
        raise AssertionError("build_orchestrator should not be called for a std_v1-configured peer")

    monkeypatch.setattr(cli_peer, "build_orchestrator", _should_not_be_called)

    with pytest.raises(ValueError, match="std_v1"):
        cli_peer.run_peer_with_gui(
            private_config_path=private_config_path,
            shared_config_path="config/shared/config_dev_g01.json",
        )


def test_run_peer_with_gui_error_message_mentions_gui(tmp_path, monkeypatch):
    private_config_path = _write_private_config(
        tmp_path, opponent_protocol="std_v1", opponent_group_id="thief-team"
    )
    monkeypatch.setattr(
        cli_peer, "build_orchestrator", lambda *a, **k: (_ for _ in ()).throw(AssertionError("unreachable"))
    )

    with pytest.raises(ValueError, match="(?i)gui"):
        cli_peer.run_peer_with_gui(
            private_config_path=private_config_path,
            shared_config_path="config/shared/config_dev_g01.json",
        )


def test_run_peer_with_gui_still_works_for_the_native_protocol(tmp_path, monkeypatch):
    # The new std_v1 check must not over-trigger on a normal native config.
    private_config_path = _write_private_config(tmp_path)
    calls = []

    def _fake_build_orchestrator(*args, **kwargs):
        calls.append(True)
        raise _StopAfterBuildOrchestratorError

    monkeypatch.setattr(cli_peer, "build_orchestrator", _fake_build_orchestrator)

    with pytest.raises(_StopAfterBuildOrchestratorError):
        cli_peer.run_peer_with_gui(
            private_config_path=private_config_path,
            shared_config_path="config/shared/config_dev_g01.json",
        )

    assert calls == [True]


class _StopAfterBuildOrchestratorError(Exception):
    """Sentinel so the native-path test can stop right after confirming
    `build_orchestrator` was reached, without actually building a real
    `LiveGuiSession`/Tk window in a headless test run."""
