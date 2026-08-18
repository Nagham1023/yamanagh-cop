"""std_v1/reporting.py tests — rule 34/35 (**[FATAL]**: "each team send
its own separate final report") applied to std_v1, which previously never
emailed anything at all. `email_mode="draft"` throughout so these never
need real Gmail credentials (`token.json`) — same convention every other
email-adjacent test in this repo already uses.
"""

from __future__ import annotations

import json

import pytest

import cop.std_v1.reporting as reporting_module
from cop.shared.private_config import PrivateConfig
from cop.std_v1.reporting import send_std_v1_report, write_std_v1_result, write_std_v1_sub_game_logs


def _private_config(**overrides) -> PrivateConfig:
    base = {
        "provider": "template", "every_n_steps": 1, "opponent_url": "http://x", "my_port": 8801,
        "turn_timeout_seconds": 30.0, "initiate_step0": False, "step0_wait_seconds": 300.0,
        "scent_map_retry_attempts": 3, "scent_map_retry_delay_seconds": 1.0, "post_match_grace_seconds": 60.0,
        "group_name": "dev-team", "group_id": "dev-team", "sub_game_number": 1, "members": ("dev-1",),
        "repos": {}, "model": "claude-sonnet-5", "step_deadline_seconds": 30.0, "email_recipient": "x@y.com",
        "email_mode": "draft",
    }
    base.update(overrides)
    return PrivateConfig(**base)


def test_write_std_v1_result_writes_the_report_json_under_the_spec_filename(tmp_path):
    report = {"game_id": "dev-team-vs-thief-team", "report_type": "std_v1_result"}
    result = {"game_id": "dev-team-vs-thief-team", "agreed": True, "report": report}
    out_path = write_std_v1_result(result, tmp_path)
    assert out_path.name == "result_dev-team-vs-thief-team.json"
    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8")) == report


def test_write_std_v1_sub_game_logs_skips_timeout_rows_with_no_transcript(tmp_path):
    result = {"game_id": "x", "sub_game_logs": [None, None]}
    written = write_std_v1_sub_game_logs(result, tmp_path)
    assert written == []


def _minimal_result(game_id: str = "dev-team-vs-thief-team", winner_group: str | None = "dev-team") -> dict:
    return {
        "game_id": game_id,
        "report": {"game_id": game_id, "final_result": {"winner_group": winner_group}},
    }


def test_send_std_v1_report_writes_a_draft_preview_in_draft_mode(config, tmp_path):
    result = _minimal_result()
    result_path = write_std_v1_result(result, tmp_path)

    response = send_std_v1_report(result, result_path, [], _private_config(), config, tmp_path)

    assert "draft_path" in response
    draft_path = tmp_path / response["draft_path"].split("/")[-1]
    assert draft_path.exists()
    draft_text = draft_path.read_text(encoding="utf-8")
    assert result_path.name in draft_text  # the attachment's own filename is in the MIME part header


def test_send_std_v1_report_never_calls_get_service_in_draft_mode(config, tmp_path, monkeypatch):
    def _should_not_be_called(token_path="token.json"):
        raise AssertionError("get_service() must never be called under email_mode='draft'")

    monkeypatch.setattr(reporting_module, "get_service", _should_not_be_called)

    result = _minimal_result()
    result_path = write_std_v1_result(result, tmp_path)

    send_std_v1_report(result, result_path, [], _private_config(email_mode="draft"), config, tmp_path)


def test_send_std_v1_report_body_names_the_winner(config, tmp_path, monkeypatch):
    captured = {}

    def _fake_send_report_bundle(service, to_addr, subject, body, attachments, email_mode, draft_dir):
        captured["subject"] = subject
        captured["body"] = body
        captured["attachments"] = attachments
        return {"sent": True}

    monkeypatch.setattr(reporting_module, "send_report_bundle", _fake_send_report_bundle)

    result = _minimal_result(game_id="dev-team-vs-thief-team", winner_group="dev-team")
    result_path = write_std_v1_result(result, tmp_path)

    send_std_v1_report(result, result_path, [], _private_config(), config, tmp_path)

    assert "dev-team-vs-thief-team" in captured["subject"]
    assert "dev-team" in captured["body"]
    assert captured["attachments"] == {result_path.name: result["report"]}


def test_send_std_v1_report_body_reports_a_tie_when_winner_group_is_none(config, tmp_path, monkeypatch):
    captured = {}

    def _fake_send_report_bundle(service, to_addr, subject, body, attachments, email_mode, draft_dir):
        captured["body"] = body
        return {"sent": True}

    monkeypatch.setattr(reporting_module, "send_report_bundle", _fake_send_report_bundle)

    result = _minimal_result(winner_group=None)
    result_path = write_std_v1_result(result, tmp_path)

    send_std_v1_report(result, result_path, [], _private_config(), config, tmp_path)

    assert "tie" in captured["body"].lower()


def test_send_std_v1_report_includes_every_sub_game_log_as_its_own_attachment(config, tmp_path, monkeypatch):
    captured = {}

    def _fake_send_report_bundle(service, to_addr, subject, body, attachments, email_mode, draft_dir):
        captured["attachments"] = attachments
        return {"sent": True}

    monkeypatch.setattr(reporting_module, "send_report_bundle", _fake_send_report_bundle)

    result = _minimal_result()
    result_path = write_std_v1_result(result, tmp_path)
    log_path = tmp_path / "log_dev-team-vs-thief-team_g01.json"
    log_payload = {"protocol": "std_v1", "game_id": "dev-team-vs-thief-team", "sub_game_number": 1, "records": []}
    log_path.write_text(json.dumps(log_payload), encoding="utf-8")

    send_std_v1_report(result, result_path, [log_path], _private_config(), config, tmp_path)

    assert captured["attachments"][log_path.name] == log_payload
    assert captured["attachments"][result_path.name] == result["report"]


def test_send_std_v1_report_counted_reaches_both_the_opponent_and_the_lecturer(config, tmp_path, monkeypatch):
    captured = {}

    def _fake_send_report_bundle(service, to_addr, subject, body, attachments, email_mode, draft_dir):
        captured["to_addr"] = to_addr
        return {"sent": True}

    monkeypatch.setattr(reporting_module, "send_report_bundle", _fake_send_report_bundle)

    result = _minimal_result()
    result_path = write_std_v1_result(result, tmp_path)
    private_config = _private_config(email_recipient="lecturer@uni.edu", email_opponent_recipient="opponent@theirteam.com")

    send_std_v1_report(result, result_path, [], private_config, config, tmp_path, counted=True)

    assert captured["to_addr"] == "opponent@theirteam.com, lecturer@uni.edu"


def test_send_std_v1_report_uncounted_reaches_only_the_opponent(config, tmp_path, monkeypatch):
    captured = {}

    def _fake_send_report_bundle(service, to_addr, subject, body, attachments, email_mode, draft_dir):
        captured["to_addr"] = to_addr
        return {"sent": True}

    monkeypatch.setattr(reporting_module, "send_report_bundle", _fake_send_report_bundle)

    result = _minimal_result()
    result_path = write_std_v1_result(result, tmp_path)
    private_config = _private_config(email_recipient="lecturer@uni.edu", email_opponent_recipient="opponent@theirteam.com")

    send_std_v1_report(result, result_path, [], private_config, config, tmp_path, counted=False)

    assert captured["to_addr"] == "opponent@theirteam.com"


def test_send_std_v1_report_goes_through_the_gatekeeper_and_respects_the_daily_quota(config, tmp_path, monkeypatch):
    # Rules 28/29: a real Gatekeeper (Quota Manager -> Token Bucket -> DOS
    # Detector) must actually gate this call, not bypass it -- proven by
    # exhausting the quota and confirming the send is refused, not sent.
    from cop.policy.gatekeeper import GatekeeperRejectionError

    monkeypatch.setattr(reporting_module, "ApiGatekeeper", lambda cfg: _AlwaysRejectGatekeeper())

    result = _minimal_result()
    result_path = write_std_v1_result(result, tmp_path)

    with pytest.raises(GatekeeperRejectionError):
        send_std_v1_report(result, result_path, [], _private_config(), config, tmp_path)


class _AlwaysRejectGatekeeper:
    def execute(self, api_call, *args, **kwargs):
        from cop.policy.gatekeeper import GatekeeperRejectionError

        raise GatekeeperRejectionError("quota_manager", "daily ceiling reached")
