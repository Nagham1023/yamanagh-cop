"""`__main__.py` — argparse + dispatch only, kept thin on purpose; the real
logic (`run_peer`/`run_replay`) has its own dedicated tests
(`test_cli_peer.py`/`test_cli_replay.py`). This file only proves the thin
wrapper itself parses args correctly and calls through to the right
function with the right arguments — monkeypatched, not a real match.
"""

from __future__ import annotations

import sys

import pytest

import cop.__main__ as main_module
from cop.orchestrator_step0 import Step0MismatchError


def test_peer_subcommand_dispatches_to_run_peer_with_parsed_flags(monkeypatch):
    captured = {}

    async def _fake_run_peer(
        private_config_path, shared_config_path, *, counted, use_tunnel, ngrok_domain, tunnel_provider
    ):
        captured["args"] = (
            private_config_path, shared_config_path, counted, use_tunnel, ngrok_domain, tunnel_provider
        )

    monkeypatch.setattr(main_module, "run_peer", _fake_run_peer)
    monkeypatch.setattr(
        sys, "argv",
        [
            "cop", "peer", "--counted", "--tunnel", "--ngrok-domain", "my-name.ngrok-free.app",
            "--tunnel-provider", "cloudflare",
            "--private-config", "a.toml", "--shared-config", "b.json",
        ],
    )

    main_module.main()

    assert captured["args"] == ("a.toml", "b.json", True, True, "my-name.ngrok-free.app", "cloudflare")


def test_peer_subcommand_defaults_to_zero_extra_flags(monkeypatch):
    captured = {}

    async def _fake_run_peer(
        private_config_path, shared_config_path, *, counted, use_tunnel, ngrok_domain, tunnel_provider
    ):
        captured["args"] = (
            private_config_path, shared_config_path, counted, use_tunnel, ngrok_domain, tunnel_provider
        )

    monkeypatch.setattr(main_module, "run_peer", _fake_run_peer)
    monkeypatch.setattr(sys, "argv", ["cop", "peer"])

    main_module.main()

    _, _, counted, use_tunnel, ngrok_domain, tunnel_provider = captured["args"]
    assert counted is False
    assert use_tunnel is False
    assert ngrok_domain is None
    assert tunnel_provider == "ngrok"


def test_peer_subcommand_exits_nonzero_on_a_step0_mismatch(monkeypatch, capsys):
    async def _fake_run_peer(*args, **kwargs):
        raise Step0MismatchError("config_sha256 mismatch")

    monkeypatch.setattr(main_module, "run_peer", _fake_run_peer)
    monkeypatch.setattr(sys, "argv", ["cop", "peer"])

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exc_info.value.code == 1
    assert "config_sha256 mismatch" in capsys.readouterr().err


def test_peer_subcommand_exits_nonzero_on_a_rule_52_violation(monkeypatch, capsys):
    # rule-auditor's own finding: league_ledger.py's ValueError (a real
    # repeat-counted-opponent violation) used to reach main() uncaught —
    # same clean exit path as Step0MismatchError now.
    async def _fake_run_peer(*args, **kwargs):
        raise ValueError("already counted a game against this opponent")

    monkeypatch.setattr(main_module, "run_peer", _fake_run_peer)
    monkeypatch.setattr(sys, "argv", ["cop", "peer"])

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exc_info.value.code == 1
    assert "already counted" in capsys.readouterr().err


def test_replay_subcommand_dispatches_to_run_replay_and_exits_with_its_code(monkeypatch):
    captured = {}

    def _fake_run_replay(log_path, *, gui):
        captured["args"] = (log_path, gui)
        return 7

    monkeypatch.setattr(main_module, "run_replay", _fake_run_replay)
    monkeypatch.setattr(sys, "argv", ["cop", "replay", "--log", "logs/log_dev_g01.json", "--gui"])

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert captured["args"] == ("logs/log_dev_g01.json", True)
    assert exc_info.value.code == 7


def test_no_subcommand_is_rejected():
    with pytest.raises(SystemExit):
        main_module._build_parser().parse_args([])


def test_peer_subcommand_with_gui_dispatches_to_run_peer_with_gui(monkeypatch):
    captured = {}

    def _fake_run_peer_with_gui(
        private_config_path, shared_config_path, *, counted, use_tunnel, ngrok_domain, tunnel_provider
    ):
        captured["args"] = (
            private_config_path, shared_config_path, counted, use_tunnel, ngrok_domain, tunnel_provider
        )

    monkeypatch.setattr(main_module, "run_peer_with_gui", _fake_run_peer_with_gui)
    monkeypatch.setattr(
        sys,
        "argv",
        ["cop", "peer", "--gui", "--private-config", "a.toml", "--shared-config", "b.json"],
    )

    main_module.main()

    assert captured["args"] == ("a.toml", "b.json", False, False, None, "ngrok")
