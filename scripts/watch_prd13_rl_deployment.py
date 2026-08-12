"""Watch PRD 13's milestone live: two real, independent `run_peer()` calls
(the exact pattern `tests/unit/test_cli_peer.py`'s own two-real-processes
test uses), one side's private config pointing `police_class` at
`RLCopBrain` — proving the dynamic loader wires a real RL brain into a
real, negotiated, played, and reported match end to end, through the
actual CLI path, not a hand-assembled `Orchestrator`.

This does NOT make `RLCopBrain` the default — `police_class` is set
explicitly in a throwaway test config here, exactly the mechanism any
`[strategy]` override already supports (Table 22). The separate promotion
commit that would ever change the *default* is out of scope for this
script and this PRD — see `PRD-13-ml-pipeline-and-deployment.md`.

Found while building this milestone, not caused by it: with barriers
enabled, both sides here (both running `CopBrain`-lineage barrier logic —
`RLCopBrain` inherits it unchanged) can each place a barrier on an
overlapping turn, each triggering an outgoing Capture Claim while also
receiving the peer's own claim — logged as `unexpected_capture_claim_received`
on both sides, followed by a mutual `TECHNICAL_LOSS` after the full
`response_timeout_seconds` wait. Reproduced directly (see
`PRD-13-ml-pipeline-and-deployment.md`'s own account), confirmed unrelated
to RL/quantization/pipeline code (pre-existing capture-claim protocol
concurrency, PRD 6/8 territory) — out of scope to fix here, so this demo
sets `max_barriers=0` to route around it rather than leave the milestone
blocked on an orchestrator-internals fix that belongs to a different layer.

Run:
    uv run python scripts/watch_prd13_rl_deployment.py
"""

from __future__ import annotations

import asyncio
import json
import socket
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from cop.cli_peer import run_peer  # noqa: E402

REAL_SHARED_CONFIG = REPO_ROOT / "config" / "shared" / "config_dev_g01.json"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _fast_shared_config(tmp_dir: Path) -> str:
    """`max_moves=2` matches `tests/unit/test_cli_peer.py::_fast_shared_config`'s
    own exact precedent, for the exact reason its docstring already gives:
    two `CopBrain`-lineage sides (both this repo, symmetric self-play — the
    only kind of opponent available without a real separate thief process)
    converge onto each other fast. `max_barriers=0` additionally sidesteps
    a real, reproduced, pre-existing bug found while building this script —
    see the module docstring's "Found while building this milestone" note —
    unrelated to PRD 11-13's own RL/quantization/pipeline code."""
    data = json.loads(REAL_SHARED_CONFIG.read_text())
    data["movement_and_barriers"]["max_moves"] = 2
    data["movement_and_barriers"]["survival_threshold"] = 2
    data["movement_and_barriers"]["max_barriers"] = 0
    path = tmp_dir / "fast_shared_config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def _write_private_config(
    tmp_dir: Path, *, group_id: str, my_port: int, opponent_port: int, initiate_step0: bool,
    police_class: str | None,
) -> str:
    strategy_section = f'\n[strategy]\npolice_class = "{police_class}"\n' if police_class else ""
    path = tmp_dir / f"game_{group_id}.toml"
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
{strategy_section}
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


async def _run_match(tmp_dir: Path):
    shared_config = _fast_shared_config(tmp_dir)
    port_rl, port_baseline = _free_port(), _free_port()
    config_rl = _write_private_config(
        tmp_dir, group_id="rl-side", my_port=port_rl, opponent_port=port_baseline,
        initiate_step0=True, police_class="cop.reasoning.rl_cop_brain:RLCopBrain",
    )
    config_baseline = _write_private_config(
        tmp_dir, group_id="baseline-side", my_port=port_baseline, opponent_port=port_rl,
        initiate_step0=False, police_class=None,
    )
    return await asyncio.gather(
        run_peer(config_rl, shared_config, log_path=str(tmp_dir / "rl_trace.jsonl")),
        run_peer(config_baseline, shared_config, log_path=str(tmp_dir / "baseline_trace.jsonl")),
    )


def main() -> None:
    print("PRD 13 milestone: RLCopBrain wired through the real CLI path, playing a real match")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        orchestrator_rl, orchestrator_baseline = asyncio.run(_run_match(tmp_dir))

        print(f"  RL side brain class:        {type(orchestrator_rl.brain).__name__}")
        print(f"  baseline side brain class:  {type(orchestrator_baseline.brain).__name__}")
        print(f"  RL side final state:        {orchestrator_rl.state_machine.state}")
        print(f"  baseline side final state:  {orchestrator_baseline.state_machine.state}")

        assert type(orchestrator_rl.brain).__name__ == "RLCopBrain"
        assert orchestrator_rl.state_machine.state != "TECHNICAL_LOSS"
        assert orchestrator_baseline.state_machine.state != "TECHNICAL_LOSS"
        print("\nA real RLCopBrain played a full negotiated match through the real CLI path. Milestone holds.")


if __name__ == "__main__":
    main()
