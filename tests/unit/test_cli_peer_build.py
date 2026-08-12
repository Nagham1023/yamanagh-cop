"""build_orchestrator: police_class wiring, with a zero-regression proof
for the unset (current, real) case — CopBrain must stay the actual default."""

from __future__ import annotations

import tomllib
from pathlib import Path

from cop.cli_peer_build import build_orchestrator
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.rl_cop_brain import RLCopBrain

_SHARED_CONFIG = "config/shared/config_dev_g01.json"


def test_no_police_class_set_still_constructs_a_cop_brain_default():
    """The real config/game.toml has no [strategy] police_class set today
    — confirmed by reading it directly, not assumed — so this is the
    actual, currently-live behavior, not just a hypothetical default."""
    raw = tomllib.loads(Path("config/game.toml").read_text(encoding="utf-8"))
    assert raw.get("strategy", {}).get("police_class") is None

    orchestrator, _private, _config, _game_id = build_orchestrator(
        "config/game.toml", _SHARED_CONFIG, log_path="/tmp/test_cli_peer_build_trace.jsonl"
    )
    assert type(orchestrator.brain) is CopBrain


def test_police_class_set_to_rl_cop_brain_loads_it(tmp_path):
    private_config_path = tmp_path / "game.toml"
    private_config_path.write_text(
        """
version = "1.10"
[game]
group_name = "dev-team"
group_id = "dev-team"
sub_game_number = 1
members = ["dev-1"]
repos = { cop = "https://example.com/cop", thief = "https://example.com/thief" }
[network]
my_port = 8801
opponent_url = "http://127.0.0.1:8802/mcp"
turn_timeout_seconds = 180
[strategy]
police_class = "cop.reasoning.rl_cop_brain:RLCopBrain"
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
    orchestrator, _private, _config, _game_id = build_orchestrator(
        str(private_config_path), _SHARED_CONFIG, log_path=str(tmp_path / "trace.jsonl")
    )
    assert type(orchestrator.brain) is RLCopBrain
