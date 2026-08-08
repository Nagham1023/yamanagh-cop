"""Ch. 9.3.1's third Gatekeeper layer: a circuit breaker on this repo's own
sending pattern. Deterministic via monkeypatching `time.monotonic`.
"""

from __future__ import annotations

import cop.policy.dos_detector as dos_detector_module
from cop.policy.dos_detector import DosDetector


def _freeze_clock(monkeypatch, start: float = 0.0):
    clock = {"now": start}
    monkeypatch.setattr(dos_detector_module.time, "monotonic", lambda: clock["now"])
    return clock


def test_consecutive_attempts_with_no_success_trips_locked(monkeypatch):
    _freeze_clock(monkeypatch)
    detector = DosDetector(consecutive_threshold=3, window_seconds=10.0)

    detector.record_attempt()
    assert detector.is_locked() is False
    detector.record_attempt()
    assert detector.is_locked() is False
    detector.record_attempt()
    assert detector.is_locked() is True


def test_a_success_in_between_resets_the_streak(monkeypatch):
    _freeze_clock(monkeypatch)
    detector = DosDetector(consecutive_threshold=3, window_seconds=10.0)

    detector.record_attempt()
    detector.record_attempt()
    detector.record_success()
    detector.record_attempt()
    detector.record_attempt()

    assert detector.is_locked() is False  # never reached 3 consecutive since the success


def test_attempts_spread_outside_the_window_do_not_accumulate(monkeypatch):
    clock = _freeze_clock(monkeypatch)
    detector = DosDetector(consecutive_threshold=3, window_seconds=10.0)

    detector.record_attempt()
    clock["now"] += 20.0  # well outside the window — a new streak starts
    detector.record_attempt()
    clock["now"] += 20.0
    detector.record_attempt()

    assert detector.is_locked() is False


def test_once_locked_further_attempts_do_not_unlock_it(monkeypatch):
    _freeze_clock(monkeypatch)
    detector = DosDetector(consecutive_threshold=2, window_seconds=10.0)

    detector.record_attempt()
    detector.record_attempt()
    assert detector.is_locked() is True

    detector.record_success()
    detector.record_attempt()
    assert detector.is_locked() is True  # only reset() clears it


def test_reset_clears_the_lock(monkeypatch):
    _freeze_clock(monkeypatch)
    detector = DosDetector(consecutive_threshold=1, window_seconds=10.0)

    detector.record_attempt()
    assert detector.is_locked() is True

    detector.reset()
    assert detector.is_locked() is False
