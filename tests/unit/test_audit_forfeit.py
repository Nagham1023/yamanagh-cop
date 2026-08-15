"""Rule 19 [FATAL] — "score 0 to the forging team" on any audit hash
mismatch, enforced automatically and symmetrically in both directions
(`orchestrator_report_entry.py::_build_sub_game_entry`'s own docstring has
the full reasoning, including why a local false-positive audit bug still
zeroes the score rather than waiting for manual review).

`_build_sub_game_entry` is tested directly — it's a pure, synchronous
method once `self_audit_passed`/`peer_audit_passed` are already known, no
need to run a full `report_game()`/network exchange to exercise it.
"""

from __future__ import annotations

import json

from cop.domain.scoring import Outcome, Score
from cop.integrity.hardware_declaration import HardwareDeclaration
from cop.integrity.step0 import Step0Declaration
from cop.orchestrator import Orchestrator
from cop.reasoning.cop_brain import CopBrain

_OPPONENT_DECLARATION = Step0Declaration(
    hardware=HardwareDeclaration(
        os_name="Linux", cpu_cores=8, ram_gb=16.0, gpu_present=False, gpu_vram_gb=None,
        llm_model="test-model",
    ),
    code_commit_hash="b" * 40,
    group_name="team-b",
    sub_game_number=1,
    config_sha256="c" * 64,
    scent_model_sha256="d" * 64,
)


def _client(config, tmp_path) -> Orchestrator:
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    client._opponent_declaration = _OPPONENT_DECLARATION
    client.trace.log("test_setup")  # aggregate_tokens needs the log file to genuinely exist
    return client


def test_a_self_audit_failure_zeroes_this_sides_own_score_and_flips_the_winner(config, tmp_path):
    client = _client(config, tmp_path)
    # Real gameplay: this side (cop) would have won a capture, 20-5.
    entry = client._build_sub_game_entry(
        Outcome.CAPTURE, Score(cop=20, thief=5), self_audit_passed=False, peer_audit_passed=True, is_counted=True
    )
    payload = entry.to_dict()

    assert entry.this_score == 0
    assert entry.opponent_score == 5
    assert payload["result"] == "capture"  # honest gameplay record, untouched
    assert payload["winner_group"] == entry.opponent_group  # forfeited despite winning on the board
    assert payload["tie"] is False


def test_a_peer_audit_failure_zeroes_the_opponents_score_and_this_side_wins(config, tmp_path):
    client = _client(config, tmp_path)
    entry = client._build_sub_game_entry(
        Outcome.SURVIVAL, Score(cop=5, thief=10), self_audit_passed=True, peer_audit_passed=False, is_counted=True
    )
    payload = entry.to_dict()

    assert entry.this_score == 5
    assert entry.opponent_score == 0
    assert payload["winner_group"] == entry.this_group


def test_both_audits_failing_zeroes_both_scores_and_produces_a_tie(config, tmp_path):
    client = _client(config, tmp_path)
    entry = client._build_sub_game_entry(
        Outcome.CAPTURE, Score(cop=20, thief=5), self_audit_passed=False, peer_audit_passed=False, is_counted=True
    )
    payload = entry.to_dict()

    assert entry.this_score == 0
    assert entry.opponent_score == 0
    assert payload["tie"] is True
    assert payload["winner_group"] is None


def test_both_audits_passing_leaves_the_real_gameplay_score_untouched(config, tmp_path):
    client = _client(config, tmp_path)
    entry = client._build_sub_game_entry(
        Outcome.CAPTURE, Score(cop=20, thief=5), self_audit_passed=True, peer_audit_passed=True, is_counted=True
    )
    payload = entry.to_dict()

    assert entry.this_score == 20
    assert entry.opponent_score == 5
    assert payload["winner_group"] == entry.this_group


def test_audit_forfeit_applied_is_logged_only_when_a_forfeit_actually_happens(config, tmp_path):
    forfeiting_client = _client(config, tmp_path)
    forfeiting_client._build_sub_game_entry(
        Outcome.SURVIVAL, Score(cop=5, thief=10), self_audit_passed=False, peer_audit_passed=True, is_counted=True
    )
    events = [
        json.loads(line)
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (forfeit_event,) = [e for e in events if e["event"] == "audit_forfeit_applied"]
    assert forfeit_event["self_forfeited"] is True
    assert forfeit_event["opponent_forfeited"] is False


def test_audit_forfeit_applied_is_not_logged_when_both_audits_pass(config, tmp_path):
    client = _client(config, tmp_path)
    client._build_sub_game_entry(
        Outcome.CAPTURE, Score(cop=20, thief=5), self_audit_passed=True, peer_audit_passed=True, is_counted=True
    )
    events = [
        json.loads(line)
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert not any(e["event"] == "audit_forfeit_applied" for e in events)
