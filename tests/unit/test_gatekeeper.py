"""`ApiGatekeeper` (`software_submission_guidelines-V3.pdf` §5.1's own
facade shape): fail-fast gate ordering, retry-on-transient-failure, and
`get_queue_status()` — all against real `TokenBucket`/`QuotaManager`/
`DosDetector` instances, not mocks of the gates themselves.
"""

from __future__ import annotations

import pytest

from cop.policy.gatekeeper import ApiGatekeeper, GatekeeperRejectionError


def test_a_call_that_clears_every_gate_reaches_the_wrapped_call(config):
    gatekeeper = ApiGatekeeper(config)
    calls = []

    result = gatekeeper.execute(lambda x: calls.append(x) or x * 2, 21)

    assert result == 42
    assert calls == [21]
    assert gatekeeper.get_queue_status().approved == 1


def test_quota_manager_rejection_never_reaches_the_wrapped_call(config):
    gatekeeper = ApiGatekeeper(config, daily_ceiling=0)
    calls = []

    with pytest.raises(GatekeeperRejectionError) as exc_info:
        gatekeeper.execute(lambda: calls.append(1))

    assert exc_info.value.gate == "quota_manager"
    assert calls == []
    assert gatekeeper.get_queue_status().rejected_by_quota_manager == 1


def test_token_bucket_rejection_never_reaches_the_wrapped_call(config):
    fast_config = config.__class__(**{**config.__dict__, "rate_limit_requests_per_minute": 60.0})
    gatekeeper = ApiGatekeeper(fast_config)
    # capacity == requests_per_minute == 60: exhaust it first.
    for _ in range(60):
        gatekeeper.execute(lambda: None)

    calls = []
    with pytest.raises(GatekeeperRejectionError) as exc_info:
        gatekeeper.execute(lambda: calls.append(1))

    assert exc_info.value.gate == "token_bucket"
    assert calls == []


def test_get_queue_status_reflects_a_rejection_that_just_happened(config):
    gatekeeper = ApiGatekeeper(config, daily_ceiling=1)
    gatekeeper.execute(lambda: None)

    with pytest.raises(GatekeeperRejectionError):
        gatekeeper.execute(lambda: None)

    status = gatekeeper.get_queue_status()
    assert status.approved == 1
    assert status.rejected_by_quota_manager == 1
    assert status.queue_depth == 0


def test_a_transient_failure_retries_with_backoff_then_succeeds(config, monkeypatch):
    import cop.policy.gatekeeper as gatekeeper_module

    sleeps = []
    monkeypatch.setattr(gatekeeper_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    gatekeeper = ApiGatekeeper(config)
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("transient failure")
        return "ok"

    result = gatekeeper.execute(flaky)

    assert result == "ok"
    assert attempts["count"] == 2
    assert sleeps == [config.rate_limit_retry_backoff_seconds]
    assert gatekeeper.get_queue_status().retries == 1


def test_dos_detector_rejection_never_reaches_the_wrapped_call(config, monkeypatch):
    # The third gate (ch. 9.3.1's own circuit breaker): five consecutive
    # attempts with no intervening success trips LOCKED. One execute() call
    # that always fails contributes max_retries+1 attempts to the streak;
    # a second call's first attempt is the one that crosses the threshold —
    # its *next* attempt is the one the DOS detector actually rejects.
    import cop.policy.gatekeeper as gatekeeper_module

    monkeypatch.setattr(gatekeeper_module.time, "sleep", lambda seconds: None)
    gatekeeper = ApiGatekeeper(config)

    def always_fails():
        raise RuntimeError("still failing")

    with pytest.raises(RuntimeError):
        gatekeeper.execute(always_fails)

    with pytest.raises(GatekeeperRejectionError) as exc_info:
        gatekeeper.execute(always_fails)

    assert exc_info.value.gate == "dos_detector"
    assert gatekeeper.get_queue_status().rejected_by_dos_detector == 1


def test_exhausting_retries_re_raises_the_original_exception(config, monkeypatch):
    import cop.policy.gatekeeper as gatekeeper_module

    monkeypatch.setattr(gatekeeper_module.time, "sleep", lambda seconds: None)
    gatekeeper = ApiGatekeeper(config)

    def always_fails():
        raise RuntimeError("permanent failure")

    with pytest.raises(RuntimeError, match="permanent failure"):
        gatekeeper.execute(always_fails)
