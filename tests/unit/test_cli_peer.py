"""`cli_peer.py::run_peer` — the CLI `peer` subcommand's real logic,
called directly (no argv needed). Two real, independent processes-worth of
config, run concurrently via `asyncio.gather`, same bilateral discipline
every other test in this repo uses (rule 1/2: never two Orchestrators in
one process's live state — two separate objects here, no shared state
between them beyond the plain HTTP calls any real two-process deployment
would also make).
"""

from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path

import pytest

from cop.cli_peer import run_peer
from cop.orchestrator_step0 import Step0MismatchError

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_SHARED_CONFIG = REPO_ROOT / "config" / "shared" / "config_dev_g01.json"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _fast_shared_config(tmp_path) -> str:
    """`max_moves`/`survival_threshold` trimmed to 2 — two real `CopBrain`
    instances playing each other (rule 1/2: never a real thief brain) have
    no reason to converge on a capture quickly; a small step ceiling keeps
    this test fast regardless, same precedent `test_orchestrator_game_loop.py`
    already uses for the same reason.

    `max_barriers` set to 0 for the same reason `scripts/watch_prd13_rl_deployment.py`
    already does: per the book, only the cop ever sends a Capture Claim, and
    only the thief is ever obligated to answer one (ch. 3.4) — this repo can
    never run a thief brain (rule 1/2), so a self-play pair here is two real
    cop-role peers with *neither* side able to legitimately answer a claim,
    not a stand-in for a real match. `PlaceBarrier` claims unconditionally
    (rule 46 — matching belief is not required), so without a real thief on
    either end, a first-turn barrier placement is an unanswerable claim and
    a guaranteed mutual `TECHNICAL_LOSS`, not a wiring bug in `run_peer()`
    itself. Disabling barriers for this CLI-wiring test sidesteps a scenario
    the protocol was never meant to face, rather than teaching the cop's own
    production code to answer claims it should never receive for real —
    that would leak this side's exact position to anyone willing to send it
    a bogus claim, since `CaptureResponse` always carries `true_thief_pos`,
    confirmed or not."""
    data = json.loads(REAL_SHARED_CONFIG.read_text())
    data["movement_and_barriers"]["max_moves"] = 2
    data["movement_and_barriers"]["survival_threshold"] = 2
    data["movement_and_barriers"]["max_barriers"] = 0
    path = tmp_path / "fast_shared_config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def _write_private_config(tmp_path, *, group_id, my_port, opponent_port, initiate_step0) -> str:
    path = tmp_path / f"game_{group_id}.toml"
    path.write_text(
        f"""
version = "1.10"
[game]
group_name = "{group_id}"
group_id = "{group_id}"
sub_game_number = 1
members = ["tester"]
repos = {{ cop = "https://example.com/{group_id}-cop", thief = "https://example.com/{group_id}-thief" }}

[network]
my_port = {my_port}
opponent_url = "http://127.0.0.1:{opponent_port}/mcp"
turn_timeout_seconds = 30
initiate_step0 = {str(initiate_step0).lower()}
step0_wait_seconds = 30

[trash_talk]
provider = "template"
every_n_steps = 1

[llm]
model = "claude-sonnet-5"
step_deadline_seconds = 30

[email]
recipient = "test@example.com"
mode = "draft"
""",
        encoding="utf-8",
    )
    return str(path)


def test_run_peer_two_real_processes_reach_a_completed_and_reported_match(tmp_path):
    shared_config = _fast_shared_config(tmp_path)
    port_a, port_b = _free_port(), _free_port()
    config_a = _write_private_config(
        tmp_path, group_id="team-a", my_port=port_a, opponent_port=port_b, initiate_step0=True
    )
    config_b = _write_private_config(
        tmp_path, group_id="team-b", my_port=port_b, opponent_port=port_a, initiate_step0=False
    )

    async def _run():
        return await asyncio.gather(
            run_peer(
                config_a, shared_config, counted=True,
                log_path=str(tmp_path / "a_trace.jsonl"), league_ledger_path=str(tmp_path / "a_ledger.json"),
            ),
            run_peer(
                config_b, shared_config, counted=True,
                log_path=str(tmp_path / "b_trace.jsonl"), league_ledger_path=str(tmp_path / "b_ledger.json"),
            ),
        )

    orchestrator_a, orchestrator_b = asyncio.run(_run())

    assert orchestrator_a.state_machine.state != "TECHNICAL_LOSS"
    assert orchestrator_b.state_machine.state != "TECHNICAL_LOSS"
    # Both sides negotiated for real, learned each other's real repos.
    assert orchestrator_a._opponent_repos == {
        "cop": "https://example.com/team-b-cop", "thief": "https://example.com/team-b-thief",
    }
    # is_counted=True actually reached the league ledger, through the real
    # report_game() call — proves --counted's own end-to-end wiring, not
    # just that the flag was accepted.
    assert orchestrator_a.league_ledger.counted_game_count() == 1
    assert (tmp_path / "a_trace.jsonl").exists()


def test_run_peer_defaults_to_uncounted_when_the_flag_is_omitted(tmp_path):
    shared_config = _fast_shared_config(tmp_path)
    port_a, port_b = _free_port(), _free_port()
    config_a = _write_private_config(
        tmp_path, group_id="team-a", my_port=port_a, opponent_port=port_b, initiate_step0=True
    )
    config_b = _write_private_config(
        tmp_path, group_id="team-b", my_port=port_b, opponent_port=port_a, initiate_step0=False
    )

    async def _run():
        return await asyncio.gather(
            run_peer(
                config_a, shared_config,
                log_path=str(tmp_path / "a_trace.jsonl"), league_ledger_path=str(tmp_path / "a_ledger.json"),
            ),
            run_peer(
                config_b, shared_config,
                log_path=str(tmp_path / "b_trace.jsonl"), league_ledger_path=str(tmp_path / "b_ledger.json"),
            ),
        )

    orchestrator_a, _orchestrator_b = asyncio.run(_run())

    assert orchestrator_a.league_ledger.counted_game_count() == 0


def test_run_peer_passive_side_times_out_cleanly_when_nobody_ever_initiates(tmp_path):
    shared_config = _fast_shared_config(tmp_path)
    lonely_port = _free_port()
    never_used_port = _free_port()
    config = tmp_path / "game_lonely.toml"
    config.write_text(
        f"""
version = "1.10"
[game]
group_name = "lonely"
group_id = "lonely"
sub_game_number = 1
members = ["tester"]
repos = {{ cop = "https://example.com/cop", thief = "https://example.com/thief" }}

[network]
my_port = {lonely_port}
opponent_url = "http://127.0.0.1:{never_used_port}/mcp"
turn_timeout_seconds = 30
initiate_step0 = false
step0_wait_seconds = 0.3

[trash_talk]
provider = "template"
every_n_steps = 1

[llm]
model = "claude-sonnet-5"
step_deadline_seconds = 30

[email]
recipient = "test@example.com"
mode = "draft"
""",
        encoding="utf-8",
    )

    with pytest.raises(Step0MismatchError):
        asyncio.run(
            run_peer(
                str(config), shared_config,
                log_path=str(tmp_path / "trace.jsonl"), league_ledger_path=str(tmp_path / "ledger.json"),
            )
        )
