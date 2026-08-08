"""`cli_replay.py::run_replay` — the CLI `replay` subcommand's real logic,
headless (rule 20 **[FATAL]**: a real grader's own situation is "just this
log file," not necessarily a display). Exercises the actual nonce-
extraction wiring end to end, not just `ReplayViewer` directly.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

from cop.cli_replay import run_replay
from cop.orchestrator import Orchestrator
from cop.reasoning.brain_base import Move
from cop.reasoning.cop_brain import CopBrain


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _completed_match_log(config, tmp_path) -> str:
    """One real committed turn plus Final Reveal — the only thing that
    produces the `nonces_revealed` event `run_replay` needs."""
    port = _free_port()
    server = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "server_trace.jsonl"))
    threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    log_path = tmp_path / "client_trace.jsonl"
    client = Orchestrator(config, CopBrain(), log_path=str(log_path))
    url = f"http://127.0.0.1:{port}/mcp"
    client.state_machine.transition("COMPUTING_MOVE")
    asyncio.run(client.commit_and_reveal_to_peer(url, Move(direction="N"), False, "quiet by the river"))
    asyncio.run(client.send_final_reveal_to_peer(url))
    return str(log_path)


def test_run_replay_exits_zero_and_prints_verified_ok_on_a_genuine_log(config, tmp_path, capsys):
    log_path = _completed_match_log(config, tmp_path)

    exit_code = run_replay(log_path)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Verified OK" in out
    assert "step 0: ok" in out


def test_run_replay_exits_one_and_prints_tampered_on_a_tampered_log(config, tmp_path, capsys):
    log_path = _completed_match_log(config, tmp_path)
    with open(log_path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    tampered = []
    for line in lines:
        entry = json.loads(line)
        if entry.get("event") == "committing":
            entry["move"] = {"type": "move", "direction": "S"}  # tampered after commit
        tampered.append(json.dumps(entry))
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(tampered) + "\n")

    exit_code = run_replay(log_path)

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "TAMPERED" in out


def test_run_replay_exits_one_with_a_clear_error_when_the_match_never_completed(config, tmp_path, capsys):
    # No Final Reveal ever happened — no nonces_revealed event exists.
    port = _free_port()
    server = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "server_trace.jsonl"))
    threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    log_path = tmp_path / "incomplete_trace.jsonl"
    client = Orchestrator(config, CopBrain(), log_path=str(log_path))
    client.state_machine.transition("COMPUTING_MOVE")
    asyncio.run(
        client.commit_and_reveal_to_peer(
            f"http://127.0.0.1:{port}/mcp", Move(direction="N"), False, "quiet by the river"
        )
    )

    exit_code = run_replay(str(log_path))

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "nonces_revealed" in err
