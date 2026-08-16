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
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from cop.cli_peer import run_peer
from cop.cli_peer_match_body import _sleep_with_heartbeats
from cop.orchestrator import Orchestrator
from cop.orchestrator_step0 import Step0MismatchError
from cop.reasoning.cop_brain import CopBrain

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_SHARED_CONFIG = REPO_ROOT / "config" / "shared" / "config_dev_g01.json"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _port_is_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        try:
            sock.connect(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _fast_shared_config(tmp_path, max_moves: int = 2) -> str:
    """`max_moves`/`survival_threshold` trimmed to 2 by default — two real `CopBrain`
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
    data["movement_and_barriers"]["max_moves"] = max_moves
    data["movement_and_barriers"]["survival_threshold"] = max_moves
    data["movement_and_barriers"]["max_barriers"] = 0
    path = tmp_path / "fast_shared_config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def _write_private_config(
    tmp_path, *, group_id, my_port, opponent_port, initiate_step0,
    post_match_grace_seconds=0.0, step0_wait_seconds=30,
) -> str:
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
step0_wait_seconds = {step0_wait_seconds}
post_match_grace_seconds = {post_match_grace_seconds}

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


def test_run_peer_keeps_its_server_reachable_through_the_post_match_grace_period(tmp_path):
    # The real bug this closes: this side's own terminal used to return to
    # the shell prompt (killing the daemon server thread with it) the
    # instant its own report_game() finished — a genuinely slower peer's
    # own later Final Reveal call then hit a bare connection refusal, even
    # though nothing was actually wrong. Side A gets a real, generous grace
    # period; side B gets none, so the total run time is dominated by A's
    # wait alone, giving a deterministic window to probe A's port mid-grace.
    shared_config = _fast_shared_config(tmp_path)
    port_a, port_b = _free_port(), _free_port()
    config_a = _write_private_config(
        tmp_path, group_id="team-a", my_port=port_a, opponent_port=port_b,
        initiate_step0=True, post_match_grace_seconds=2.0,
    )
    config_b = _write_private_config(
        tmp_path, group_id="team-b", my_port=port_b, opponent_port=port_a,
        initiate_step0=False, post_match_grace_seconds=0.0,
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

    start = time.monotonic()
    driver = threading.Thread(target=lambda: asyncio.run(_run()))
    driver.start()

    time.sleep(1.0)  # mid-grace-period: the real match itself (max_moves=2) finishes well under this
    assert _port_is_listening(port_a), (
        "a peer arriving mid-grace-period must still reach this side — this is the whole point"
    )

    driver.join(timeout=10)
    elapsed = time.monotonic() - start
    assert not driver.is_alive(), "the grace period must actually end, not hang forever"
    # The daemon server thread itself only dies with the whole OS process
    # (real `uv run python -m cop peer` usage exits it; a single pytest
    # process never does) — not observable in-process, so the actual proof
    # the wait ran to completion, rather than being skipped, is timing.
    assert elapsed >= 2.0, "run_peer() must not return before its own configured grace period elapses"


def test_run_peer_terminates_its_own_tunnel_process_when_the_match_ends(tmp_path, monkeypatch):
    # The real bug this closes: run_as_server's own `finally:
    # stop_tunnel_if_running()` lives on the daemon thread blocking inside
    # `self.server.run(...)`, which never returns under normal shutdown —
    # so without an explicit main-thread call (added to run_match_body),
    # the tunnel's own child process (a real ngrok agent, for a real
    # match) was orphaned every time. Found live: an orphaned agent kept
    # routing to a now-dead local server (ngrok's own ERR_NGROK_8012) and
    # permanently blocked every later launch (ERR_NGROK_334, "already
    # online") until manually killed. A real subprocess stands in for
    # ngrok here — `test_orchestrator_tunnel.py`'s own synchronous
    # `run_as_server` tests can't catch this, since they never go through
    # the daemon-thread path this bug actually lived in.
    import cop.orchestrator_server as server_module
    from cop.tools.tunnel import Tunnel

    shared_config = _fast_shared_config(tmp_path)
    port_a, port_b = _free_port(), _free_port()
    config_a = _write_private_config(
        tmp_path, group_id="team-a", my_port=port_a, opponent_port=port_b,
        initiate_step0=True, post_match_grace_seconds=0.0,
    )
    config_b = _write_private_config(
        tmp_path, group_id="team-b", my_port=port_b, opponent_port=port_a,
        initiate_step0=False, post_match_grace_seconds=0.0,
    )

    placeholder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    monkeypatch.setattr(
        server_module, "start_tunnel",
        lambda port, domain=None, log_path=None: Tunnel(
            process=placeholder, public_url="https://stand-in.example.com"
        ),
    )

    async def _run():
        return await asyncio.gather(
            run_peer(
                config_a, shared_config, use_tunnel=True,
                log_path=str(tmp_path / "a_trace.jsonl"), league_ledger_path=str(tmp_path / "a_ledger.json"),
            ),
            run_peer(
                config_b, shared_config,
                log_path=str(tmp_path / "b_trace.jsonl"), league_ledger_path=str(tmp_path / "b_ledger.json"),
            ),
        )

    try:
        asyncio.run(_run())
        assert placeholder.poll() is not None, "the tunnel's own process must be terminated, not orphaned"
    finally:
        if placeholder.poll() is None:
            placeholder.terminate()


def test_run_peer_reuses_one_connection_across_many_rounds_not_one_per_call(tmp_path, monkeypatch):
    # The actual proof this whole PeerConnection refactor exists for: a
    # real cross-machine match kept failing consistently around round 5-6
    # because every single outbound call opened its own fresh
    # `fastmcp.Client` — by round 8 alone the old pattern would have
    # constructed dozens (3+ calls/round x 8 rounds x 2 sides). A real,
    # several-round match here must construct exactly one `Client` per
    # side, reused for every call, not one per call.
    import cop.tools.peer_connection as pc_module

    construct_count = {"n": 0}
    original_init = pc_module.Client.__init__

    def _counting_init(self, *args, **kwargs):
        construct_count["n"] += 1
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(pc_module.Client, "__init__", _counting_init)

    shared_config = _fast_shared_config(tmp_path, max_moves=8)
    port_a, port_b = _free_port(), _free_port()
    config_a = _write_private_config(
        tmp_path, group_id="team-a", my_port=port_a, opponent_port=port_b,
        initiate_step0=True, post_match_grace_seconds=0.0,
    )
    config_b = _write_private_config(
        tmp_path, group_id="team-b", my_port=port_b, opponent_port=port_a,
        initiate_step0=False, post_match_grace_seconds=0.0,
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

    asyncio.run(_run())

    assert construct_count["n"] == 2, (
        f"expected exactly one fastmcp.Client construction per side (2 total), got {construct_count['n']}"
    )


def test_run_peer_still_terminates_its_tunnel_process_when_the_match_raises(tmp_path, monkeypatch):
    # The real bug this closes: a Ctrl+C or any other exception during a
    # match used to skip tunnel/connection teardown entirely, since those
    # calls only sat on the normal-completion path — leaving the ngrok
    # child process orphaned, still claiming the domain for every later
    # launch (ERR_NGROK_334). Reuses the existing "nobody ever initiates"
    # scenario (a real, already-proven Step0MismatchError) specifically
    # because it's a genuine exception path, not a contrived one.
    import cop.orchestrator_server as server_module
    from cop.tools.tunnel import Tunnel

    shared_config = _fast_shared_config(tmp_path)
    lonely_port = _free_port()
    never_used_port = _free_port()
    config = _write_private_config(
        tmp_path, group_id="lonely", my_port=lonely_port, opponent_port=never_used_port,
        initiate_step0=False, post_match_grace_seconds=0.0, step0_wait_seconds=0.3,
    )

    placeholder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    monkeypatch.setattr(
        server_module, "start_tunnel",
        lambda port, domain=None, log_path=None: Tunnel(
            process=placeholder, public_url="https://stand-in.example.com"
        ),
    )

    try:
        with pytest.raises(Step0MismatchError):
            asyncio.run(
                run_peer(
                    config, shared_config, use_tunnel=True,
                    log_path=str(tmp_path / "trace.jsonl"), league_ledger_path=str(tmp_path / "ledger.json"),
                )
            )
        assert placeholder.poll() is not None, (
            "the tunnel's own process must still be terminated when the match raises, not orphaned"
        )
    finally:
        if placeholder.poll() is None:
            placeholder.terminate()


def test_sleep_with_heartbeats_keeps_the_watchdog_alive_through_a_wait_longer_than_its_own_threshold(
    config, tmp_path
):
    # The real bug this closes: watchdog_threshold_seconds (negotiated,
    # e.g. 60s) and post_match_grace_seconds (private, also 60s by
    # default) can genuinely coincide, and the watchdog's own clock starts
    # from the *last real heartbeat* — well before this deliberate wait
    # even begins. A bare asyncio.sleep let the watchdog go stale
    # mid-wait, firing os._exit(1) and skipping every pending finally
    # block. A short threshold here, with the total wait well past it,
    # proves the periodic heartbeat keeps the watchdog "ALIVE" throughout —
    # a bare sleep would have left it stale (and, in the real os._exit(1)
    # path, would have killed the process before this assertion ever ran).
    fast_config = config.__class__(**{**config.__dict__, "watchdog_threshold_seconds": 0.3})
    orchestrator = Orchestrator(fast_config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))

    asyncio.run(_sleep_with_heartbeats(orchestrator, 1.0))

    assert orchestrator.watchdog.check() == "ALIVE"
