"""Operational trace log: one JSON line per event, real file, real content."""

from __future__ import annotations

import json

from cop.observability.trace import Trace


def test_log_writes_one_readable_json_line(tmp_path):
    trace = Trace(tmp_path / "trace.jsonl")
    trace.log("deadline_expired", peer="opponent", timeout_seconds=30.0)

    lines = (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["event"] == "deadline_expired"
    assert entry["peer"] == "opponent"
    assert entry["timeout_seconds"] == 30.0
    assert "time" in entry


def test_log_appends_rather_than_overwrites(tmp_path):
    trace = Trace(tmp_path / "trace.jsonl")
    trace.log("first_event")
    trace.log("second_event")

    lines = (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "first_event"
    assert json.loads(lines[1])["event"] == "second_event"


def test_creates_parent_directory_if_missing(tmp_path):
    nested = tmp_path / "logs" / "nested" / "trace.jsonl"
    trace = Trace(nested)
    trace.log("survives_missing_dir")
    assert nested.exists()
