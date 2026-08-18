"""Rule 30 **[FATAL]** (send-only scope), rule 34 **[FATAL]** (attached JSON,
never body text). `service` is always a fake/mock here — no real Gmail
credentials exist in this test environment; `get_service`'s own OAuth flow
is a one-time, human-present step this suite can't exercise (documented in
`gmail_sender.py`'s own docstring), not something worth mocking `google.oauth2`
this deeply for.
"""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

from cop.policy.gatekeeper import ApiGatekeeper
from cop.tools.gmail_sender import (
    SCOPES,
    build_message,
    build_recipients,
    send_report,
    send_report_bundle,
)


class _FakeMessagesResource:
    def __init__(self, fail_times: int = 0):
        self.calls = []
        self._fail_times = fail_times

    def send(self, userId, body):  # noqa: N803 - matches the real Gmail API's own parameter name
        return _FakeExecutable(self, userId, body)


class _FakeExecutable:
    def __init__(self, resource: _FakeMessagesResource, user_id: str, body: dict):
        self._resource = resource
        self._user_id = user_id
        self._body = body

    def execute(self):
        self._resource.calls.append(self._body)
        if len(self._resource.calls) <= self._resource._fail_times:
            raise RuntimeError("429 Too Many Requests")
        return {"id": "fake-message-id"}


class _FakeUsersResource:
    def __init__(self, messages_resource: _FakeMessagesResource):
        self._messages = messages_resource

    def messages(self):
        return self._messages


class _FakeService:
    def __init__(self, fail_times: int = 0):
        self._messages = _FakeMessagesResource(fail_times=fail_times)

    def users(self):
        return _FakeUsersResource(self._messages)


def test_scopes_is_exactly_send_only():
    assert SCOPES == ["https://www.googleapis.com/auth/gmail.send"]


def test_build_recipients_without_an_opponent_address_keeps_the_old_single_recipient_behavior():
    assert build_recipients("prof@uni.edu", None, is_counted=True) == "prof@uni.edu"
    assert build_recipients("prof@uni.edu", None, is_counted=False) == "prof@uni.edu"


def test_build_recipients_counted_reaches_both_the_opponent_and_the_lecturer():
    result = build_recipients("prof@uni.edu", "opponent@team.com", is_counted=True)
    assert result == "opponent@team.com, prof@uni.edu"


def test_build_recipients_uncounted_reaches_only_the_opponent_never_the_lecturer():
    result = build_recipients("prof@uni.edu", "opponent@team.com", is_counted=False)
    assert result == "opponent@team.com"
    assert "prof@uni.edu" not in result


def test_send_report_attaches_exactly_one_json_part_and_a_separate_text_part():
    message = build_message(
        "grader@example.com", "Game summary", "A short note.", {"result_g01.json": {"score": 20}}
    )

    parts = message.get_payload()
    assert len(parts) == 2
    text_part, attachment_part = parts
    assert text_part.get_content_type() == "text/plain"
    assert attachment_part.get_content_type() == "application/json"
    assert attachment_part.get_filename() == "result_g01.json"
    assert json.loads(attachment_part.get_payload(decode=True)) == {"score": 20}


def test_send_report_bundle_attaches_all_four_files_in_one_message():
    attachments = {
        "declaration_g01.json": {"a": 1},
        "config_g01_g01.json": {"b": 2},
        "log_g01_g01.json": {"c": 3},
        "result_g01.json": {"d": 4},
    }
    message = build_message("grader@example.com", "subject", "body", attachments)

    parts = message.get_payload()
    attachment_parts = [p for p in parts if p.get_content_type() == "application/json"]
    assert len(attachment_parts) == 4
    assert {p.get_filename() for p in attachment_parts} == set(attachments)


def test_send_report_in_draft_mode_never_calls_gmail_send(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service = _FakeService()
    result = send_report(
        service, "grader@example.com", "subject", "body", {"a": 1}, "result_g01.json", email_mode="draft"
    )
    assert service._messages.calls == []
    draft_path = Path(result["draft_path"])
    assert draft_path.exists()
    assert "subject" in draft_path.read_text(encoding="utf-8")


def test_send_report_in_send_mode_calls_gmail_send_exactly_once():
    service = _FakeService()
    result = send_report(
        service, "grader@example.com", "subject", "body", {"a": 1}, "result_g01.json", email_mode="send"
    )
    assert result == {"id": "fake-message-id"}
    assert len(service._messages.calls) == 1


def test_send_report_bundle_in_draft_mode_never_calls_gmail_send(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service = _FakeService()
    result = send_report_bundle(
        service, "grader@example.com", "subject", "body", {"a.json": {}}, email_mode="draft"
    )
    assert service._messages.calls == []
    draft_path = Path(result["draft_path"])
    assert draft_path.exists()
    assert "subject" in draft_path.read_text(encoding="utf-8")


def test_send_report_bundle_in_send_mode_calls_gmail_send_exactly_once():
    service = _FakeService()
    result = send_report_bundle(
        service, "grader@example.com", "subject", "body", {"a.json": {}}, email_mode="send"
    )
    assert result == {"id": "fake-message-id"}
    assert len(service._messages.calls) == 1


def test_a_transient_failure_through_the_gatekeeper_retries_then_succeeds(config):
    """The real integration point TODO7 §7 names: send_report itself has no
    retry logic (gmail_sender.py's own docstring) — ApiGatekeeper.execute()
    provides it, per rule 28's own "respect a 429, never retry blindly.\""""
    import cop.policy.gatekeeper as gatekeeper_module

    service = _FakeService(fail_times=1)  # first attempt raises, second succeeds
    gatekeeper = ApiGatekeeper(config)

    with unittest.mock.patch.object(gatekeeper_module.time, "sleep"):
        result = gatekeeper.execute(
            send_report, service, "grader@example.com", "subject", "body", {"a": 1}, "result_g01.json"
        )

    assert result == {"id": "fake-message-id"}
    assert len(service._messages.calls) == 2
    assert gatekeeper.get_queue_status().retries == 1
