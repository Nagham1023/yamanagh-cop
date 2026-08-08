"""Ch. 9.3.1's first Gatekeeper layer: a daily safety ceiling, resetting at
UTC calendar-day boundaries — deterministic via monkeypatching `_today()`,
not real clock waits.
"""

from __future__ import annotations

import datetime

import cop.policy.quota_manager as quota_manager_module
from cop.policy.quota_manager import QuotaManager


def _freeze_day(monkeypatch, day: datetime.date):
    monkeypatch.setattr(quota_manager_module, "_today", lambda: day)


def test_allows_requests_up_to_the_daily_ceiling_then_blocks(monkeypatch):
    _freeze_day(monkeypatch, datetime.date(2026, 1, 1))
    manager = QuotaManager(daily_ceiling=3)

    assert manager.allow() is True
    assert manager.allow() is True
    assert manager.allow() is True
    assert manager.allow() is False
    assert manager.count_today == 3


def test_the_count_resets_on_a_new_utc_day(monkeypatch):
    _freeze_day(monkeypatch, datetime.date(2026, 1, 1))
    manager = QuotaManager(daily_ceiling=1)

    assert manager.allow() is True
    assert manager.allow() is False  # today's ceiling spent

    _freeze_day(monkeypatch, datetime.date(2026, 1, 2))
    assert manager.allow() is True  # new day, fresh ceiling
    assert manager.count_today == 1
