"""std_v1/wire.py tests — exact tool names and argument-wrapping keys
(spec Section 7): `submit_audit` alone takes `payload`, every other tool
takes `message`."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from cop.std_v1.wire import send_audit, send_control, send_negotiate, send_turn


@dataclass
class _Result:
    data: Any


class _SpyConnection:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, arguments: dict) -> _Result:
        self.calls.append((name, arguments))
        return _Result(data={"ok": True})


def test_send_negotiate_wraps_in_message():
    connection = _SpyConnection()
    asyncio.run(send_negotiate(connection, {"group_id": "g"}))
    assert connection.calls == [("negotiate", {"message": {"group_id": "g"}})]


def test_send_turn_wraps_in_message():
    connection = _SpyConnection()
    asyncio.run(send_turn(connection, {"step": 2}))
    assert connection.calls == [("receive_turn", {"message": {"step": 2}})]


def test_send_audit_wraps_in_payload_not_message():
    connection = _SpyConnection()
    asyncio.run(send_audit(connection, {"result_claim": "capture"}))
    assert connection.calls == [("submit_audit", {"payload": {"result_claim": "capture"}})]


def test_send_control_wraps_in_message():
    connection = _SpyConnection()
    asyncio.run(send_control(connection, {"type": "ping"}))
    assert connection.calls == [("receive_control", {"message": {"type": "ping"}})]


def test_send_negotiate_returns_the_response_data():
    connection = _SpyConnection()
    result = asyncio.run(send_negotiate(connection, {}))
    assert result == {"ok": True}


class _FailsOnceThenSucceedsConnection:
    """The peer's own server isn't listening yet on the very first call —
    a real, live-observed race at match startup, not a hypothetical. The
    real `fastmcp.Client._connect()` chains the underlying `httpx`
    exception as `__cause__` (`peer_connection.py::is_connect_only_failure`'s
    own docstring), so this fake reproduces that exact shape rather than a
    bare `RuntimeError`."""

    def __init__(self):
        self.attempts = 0

    async def call_tool(self, name, arguments):
        self.attempts += 1
        if self.attempts == 1:
            try:
                raise httpx.ConnectError("connection refused")
            except httpx.ConnectError as exc:
                raise RuntimeError("Client failed to connect: All connection attempts failed") from exc
        return _Result(data={"ok": True})


def test_send_negotiate_retries_past_a_connect_only_failure():
    connection = _FailsOnceThenSucceedsConnection()
    result = asyncio.run(send_negotiate(connection, {}))
    assert result == {"ok": True}
    assert connection.attempts == 2
