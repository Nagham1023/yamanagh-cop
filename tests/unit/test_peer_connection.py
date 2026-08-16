"""`PeerConnection` (`tools/peer_connection.py`) — the persistent,
auto-healing connection that replaced "one `fastmcp.Client` per call"
this session, against a real thread-hosted FastMCP server (same pattern
`test_mcp_client*.py` already use). `Client.__aenter__` is counted via a
thin monkeypatch, not mocked away — every call still does a genuine HTTP
round trip.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import httpx
import pytest
from fastmcp.exceptions import ToolError

from cop.tools import peer_connection as pc_module
from cop.tools.mcp_server import build_server
from cop.tools.peer_connection import PeerConnection, is_connect_only_failure


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_server(config, port: int | None = None) -> str:
    port = port if port is not None else _free_port()
    mcp = build_server(config)
    threading.Thread(
        target=mcp.run,
        kwargs={"transport": "http", "host": "127.0.0.1", "port": port, "show_banner": False},
        daemon=True,
    ).start()
    time.sleep(0.5)
    return f"http://127.0.0.1:{port}/mcp"


def _count_connects(monkeypatch) -> dict[str, int]:
    """Counts real `Client.__aenter__` calls (the actual connect/session
    handshake) without mocking it away — the underlying connect still runs."""
    counts = {"n": 0}
    original_aenter = pc_module.Client.__aenter__

    async def _counting_aenter(self):
        counts["n"] += 1
        return await original_aenter(self)

    monkeypatch.setattr(pc_module.Client, "__aenter__", _counting_aenter)
    return counts


def test_call_tool_reuses_one_session_across_multiple_calls(config, monkeypatch):
    counts = _count_connects(monkeypatch)
    url = _start_server(config)
    connection = PeerConnection(url)

    async def _two_calls():
        await connection.call_tool("share_scent_map", {})
        await connection.call_tool("share_scent_map", {})

    asyncio.run(_two_calls())

    assert counts["n"] == 1, "two calls through one PeerConnection must open exactly one session"


def test_a_tool_error_does_not_force_a_reconnect(config, monkeypatch):
    counts = _count_connects(monkeypatch)
    url = _start_server(config)
    connection = PeerConnection(url)

    async def _sequence():
        with pytest.raises(ToolError):
            await connection.call_tool("receive_commit", {})  # missing required h_commit
        await connection.call_tool("share_scent_map", {})  # must still work, same session

    asyncio.run(_sequence())

    assert counts["n"] == 1, "a normal tool-level rejection must not force a reconnect"


def test_a_connection_failure_forces_a_fresh_session_on_the_next_call(config):
    # Same shape as test_orchestrator_peer_failures.py's own recovery
    # test: nothing listens yet, the first call fails for real, then a
    # real server starts on that exact port — the next call must succeed
    # rather than re-raising the same cached dead-session failure.
    port = _free_port()
    connection = PeerConnection(f"http://127.0.0.1:{port}/mcp")

    async def _sequence(config):
        with pytest.raises(Exception):  # noqa: B017 - any connection failure counts
            await connection.call_tool("share_scent_map", {})
        _start_server(config, port=port)
        return await connection.call_tool("share_scent_map", {})

    result = asyncio.run(_sequence(config))

    assert result is not None


def test_is_connect_only_failure_true_for_a_raw_httpx_connect_error():
    # The real match failure this classifier exists to catch: a bare
    # ConnectError surfacing from an already-"connected" PeerConnection
    # (the pooled transport's own reconnect attempt failing), not just
    # the first-ever handshake.
    assert is_connect_only_failure(httpx.ConnectError("refused")) is True


def test_is_connect_only_failure_true_for_a_connect_timeout():
    assert is_connect_only_failure(httpx.ConnectTimeout("timed out")) is True


def test_is_connect_only_failure_true_for_fastmcp_client_own_wrapped_message():
    # `Client._connect()` wraps a first-connect failure as
    # RuntimeError("Client failed to connect: ...") chained via `from`.
    cause = httpx.ConnectError("refused")
    wrapped = RuntimeError(f"Client failed to connect: {cause}")
    wrapped.__cause__ = cause
    assert is_connect_only_failure(wrapped) is True


def test_is_connect_only_failure_true_for_the_session_not_connected_message():
    # The second real-match failure this classifier had to grow to cover:
    # `Client.session`'s own property getter raises this verbatim, before
    # `self.session.call_tool(...)` can even construct the outbound call --
    # a narrow fastmcp-internal race under a flaky tunnel, not a bare
    # ConnectError, but still provably "nothing was sent."
    exc = RuntimeError("Client is not connected. Use the 'async with client:' context manager first.")
    assert is_connect_only_failure(exc) is True


def test_is_connect_only_failure_false_for_a_data_transfer_phase_error():
    # ReadTimeout/WriteError etc. mean bytes were already in flight -- the
    # peer may have already received and applied the call, so this must
    # NOT be classified as safe to blindly retry.
    assert is_connect_only_failure(httpx.ReadTimeout("no response")) is False


def test_is_connect_only_failure_false_for_an_unrelated_runtime_error():
    assert is_connect_only_failure(RuntimeError("something else entirely")) is False


def test_close_is_idempotent_and_safe_with_no_prior_connection():
    connection = PeerConnection("http://127.0.0.1:1/mcp")  # never connected
    asyncio.run(connection.close())
    asyncio.run(connection.close())  # second call must not raise


def test_close_is_idempotent_after_a_real_connection(config):
    url = _start_server(config)
    connection = PeerConnection(url)

    async def _sequence():
        await connection.call_tool("share_scent_map", {})
        await connection.close()
        await connection.close()  # second call must not raise

    asyncio.run(_sequence())
