"""Watchdog (rule 7): ALIVE on a recent heartbeat, persist+shutdown on a stale one.

The clock is mocked (a plain counter, not `time.monotonic`) so these tests
run instantly instead of sleeping past the real threshold.
"""

from __future__ import annotations

from cop.planner.watchdog import Watchdog


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_recent_heartbeat_is_alive_and_does_not_trigger_recovery():
    clock = FakeClock()
    persisted = []
    shutdown = []
    watchdog = Watchdog(
        threshold_seconds=60.0,
        persist_state=lambda: persisted.append(True),
        controlled_shutdown=lambda: shutdown.append(True),
        clock=clock,
    )

    clock.now = 30.0  # well within the 60s threshold
    assert watchdog.check() == "ALIVE"
    assert persisted == []
    assert shutdown == []


def test_stale_heartbeat_triggers_persist_and_controlled_shutdown():
    clock = FakeClock()
    persisted = []
    shutdown = []
    watchdog = Watchdog(
        threshold_seconds=60.0,
        persist_state=lambda: persisted.append(True),
        controlled_shutdown=lambda: shutdown.append(True),
        clock=clock,
    )

    clock.now = 61.0  # past the threshold, no heartbeat() call in between
    assert watchdog.check() == "SHUTDOWN"
    assert persisted == [True]
    assert shutdown == [True]


def test_heartbeat_resets_the_staleness_clock():
    clock = FakeClock()
    watchdog = Watchdog(
        threshold_seconds=60.0,
        persist_state=lambda: None,
        controlled_shutdown=lambda: None,
        clock=clock,
    )

    clock.now = 55.0
    watchdog.heartbeat()  # main loop checked in
    clock.now = 100.0  # 45s since the heartbeat, not 100s since construction
    assert watchdog.check() == "ALIVE"
