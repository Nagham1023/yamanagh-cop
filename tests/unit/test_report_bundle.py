"""Table 20's four-file bundle: `declaration_<game_id>.json` and
`result_<game_id>.json` (the two PRD 7 builds), plus a direct check that a
real game's trace log actually lands under the correct
`log_<game_id>_g<NN>.json` name — `PLAN.md` previously (incorrectly)
claimed this already matched; checked against the real source here, not
assumed.
"""

from __future__ import annotations

import json

from cop.integrity.hardware_declaration import HardwareDeclaration
from cop.integrity.step0 import Step0Declaration
from cop.orchestrator import Orchestrator
from cop.reasoning.cop_brain import CopBrain
from cop.tools.report_bundle import (
    DeclarationBundle,
    build_declaration,
    config_filename,
    declaration_filename,
    load_config_dict,
    load_log_entries,
    log_filename,
    result_filename,
)


def _step0() -> Step0Declaration:
    hardware = HardwareDeclaration(
        os_name="Linux", cpu_cores=8, ram_gb=16.0, gpu_present=False, gpu_vram_gb=None,
        llm_model="claude-sonnet-5",
    )
    return Step0Declaration(
        hardware=hardware, code_commit_hash="a" * 40, group_name="yamanagh",
        sub_game_number=1, config_sha256="b" * 64, scent_model_sha256="c" * 64,
    )


def test_declaration_filename_matches_table_20_exactly():
    assert declaration_filename("dev") == "declaration_dev.json"


def test_result_filename_matches_table_20_exactly():
    assert result_filename("dev") == "result_dev.json"


def test_config_and_log_filenames_match_table_20_exactly():
    assert config_filename("dev", 1) == "config_dev_g01.json"
    assert log_filename("dev", 1) == "log_dev_g01.json"
    assert config_filename("dev", 12) == "config_dev_g12.json"


def test_build_declaration_round_trips_through_json_cleanly():
    bundle = DeclarationBundle(
        step0=_step0(),
        group_name="yamanagh",
        members=("nagham",),
        cop_repo_url="https://github.com/Nagham1023/yamanagh-cop",
        thief_repo_url="https://github.com/Nagham1023/yamanagh-thief",
        token_budget_per_series=200_000,
        started_at="2026-01-01T00:00:00Z",
    )
    payload = build_declaration(bundle)

    round_tripped = json.loads(json.dumps(payload))
    assert round_tripped == payload
    assert round_tripped["group_name"] == "yamanagh"
    assert round_tripped["cop_repo_url"] == "https://github.com/Nagham1023/yamanagh-cop"
    assert round_tripped["scent_model_sha256"] == "c" * 64


def test_load_config_dict_returns_the_real_negotiated_config_as_is(tmp_path):
    config_path = tmp_path / "config_dev_g01.json"
    original = {"schema_version": "1.2", "board_and_agents": {"grid_size": 7}}
    config_path.write_text(json.dumps(original), encoding="utf-8")

    assert load_config_dict(config_path) == original


def test_load_log_entries_parses_a_real_jsonl_trace_into_a_list(config, tmp_path):
    log_path = tmp_path / "log_dev_g01.json"
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(log_path))
    orchestrator.trace.log("game_started")
    orchestrator.trace.log("computed_move", action="Move(N)")

    entries = load_log_entries(log_path)

    assert [e["event"] for e in entries] == ["game_started", "computed_move"]
    assert entries[1]["action"] == "Move(N)"


def test_load_log_entries_skips_blank_lines(tmp_path):
    log_path = tmp_path / "log.json"
    log_path.write_text('{"event": "a"}\n\n{"event": "b"}\n', encoding="utf-8")

    entries = load_log_entries(log_path)

    assert [e["event"] for e in entries] == ["a", "b"]


def test_a_real_orchestrators_trace_log_lands_under_the_correct_table_20_name(config, tmp_path):
    game_id = "dev"
    sub_game_number = 1
    log_path = tmp_path / log_filename(game_id, sub_game_number)

    orchestrator = Orchestrator(config, CopBrain(), log_path=str(log_path))
    orchestrator.trace.log("game_started")

    assert log_path.exists()
    assert log_path.name == "log_dev_g01.json"
