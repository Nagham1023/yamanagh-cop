"""StdExchange: the std_v1 protocol's cross-thread mailbox — a plain
`threading.Lock` + bounded poll loop, not `asyncio.Event`. The writer is
the FastMCP server (`server_registration.py`'s sync tool handlers, run on
FastMCP's own worker thread); the reader is the async client-role loop
(`round_loop.py`/`handshake.py`/`audit.py`), which awaits these blocking
waits via `asyncio.to_thread` rather than making this class itself
asyncio-native — a plain `Lock` is safe across threads regardless of which
thread owns the event loop, unlike `asyncio.Event`, which is not
thread-safe to set from a different thread without `call_soon_threadsafe`.

Negotiation offers and audit envelopes both have a spec-mandated "a
message without its own `sub_game_number` is accepted on arrival, for
whichever sub-game is currently being waited on" rule (Section 3/10) —
modeled here as a `None`-keyed bucket checked alongside the exact key.

`_turns` is keyed by `step` alone, and every sub-game's own step counter
restarts at 1 (Section 9) — unlike `_offers`/`_audits`, which are already
naturally scoped by `sub_game_number` itself. Found via a real two-repo
match: sub-game 1 audited clean, but every single record in sub-games 2-6
came back "tampered" — `wait_for_turn(1, ...)` for sub-game 2 was
instantly returning sub-game 1's own leftover step-1 message, still
sitting in `_turns` from before, rather than actually waiting for the new
one. `series_runner.play_series` must call `reset_turns()` at the start
of every sub-game to close this."""

from __future__ import annotations

import threading
import time

from ..planner.deadline import DeadlineExceededError


class StdExchange:
    def __init__(self, poll_interval: float = 0.05) -> None:
        """`poll_interval` is a bounded busy-wait cadence, not a real
        blocking wake-up — deliberately short so a real match's own
        `wait_for_turn` returns promptly once the peer's call lands."""
        self._poll_interval = poll_interval
        self._lock = threading.Lock()
        self._offers: dict[int | None, dict] = {}
        self._turns: dict[int, dict] = {}
        self._audits: dict[int | None, dict] = {}
        self._controls: list[dict] = []

    def record_offer(self, message: dict) -> None:
        """Called from the `negotiate` tool handler on arrival."""
        with self._lock:
            self._offers[message.get("sub_game_number")] = message

    def wait_for_offer(self, sub_game_number: int, timeout: float) -> dict:
        """Blocks (this thread only) until the peer's negotiation offer
        for `sub_game_number` has arrived, or raises on timeout."""
        return self._wait_for_either_key(self._offers, sub_game_number, timeout, "negotiation offer")

    def record_turn(self, message: dict) -> None:
        """Called from the `receive_turn` tool handler on arrival."""
        with self._lock:
            self._turns[message["step"]] = message

    def wait_for_turn(self, step: int, timeout: float) -> dict:
        """Blocks until the peer's turn message for `step` has arrived."""
        return self._wait_for(self._turns, step, timeout, "turn")

    def reset_turns(self) -> None:
        """Clears every recorded turn — must be called once per sub-game,
        before that sub-game's own `play_sub_game` starts waiting, so a
        leftover message from the *previous* sub-game's identical step
        number can never be mistaken for the new one (see this class's
        own docstring)."""
        with self._lock:
            self._turns = {}

    def record_audit(self, message: dict) -> None:
        """Called from the `submit_audit` tool handler on arrival — a
        per-sub-game audit envelope or the final consensus envelope alike."""
        with self._lock:
            self._audits[message.get("sub_game_number")] = message

    def wait_for_audit(self, sub_game_number: int, timeout: float) -> dict:
        """Blocks until the peer's per-sub-game audit envelope has arrived."""
        return self._wait_for_either_key(self._audits, sub_game_number, timeout, "audit envelope")

    def wait_for_consensus(self, timeout: float) -> dict:
        """The final `series_consensus` envelope carries no
        `sub_game_number` at all — always the `None`-keyed bucket."""
        return self._wait_for(self._audits, None, timeout, "consensus envelope")

    def record_control(self, message: dict) -> None:
        """Called from the `receive_control` tool handler on arrival."""
        with self._lock:
            self._controls.append(message)

    def latest_control(self) -> dict | None:
        """The most recently received control message, or `None`."""
        with self._lock:
            return self._controls[-1] if self._controls else None

    def _wait_for(self, store: dict, key: object, timeout: float, kind: str) -> dict:
        """Shared bounded poll: checks `store[key]` on a fixed cadence
        until it appears or `timeout` elapses."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if key in store:
                    return store[key]
            time.sleep(self._poll_interval)
        raise DeadlineExceededError(f"No {kind} received (key={key!r}) within {timeout}s")

    def _wait_for_either_key(self, store: dict, key: object, timeout: float, kind: str) -> dict:
        """Same as `_wait_for`, but also accepts a `None`-keyed entry —
        the "no `sub_game_number` on this message" case."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if key in store:
                    return store[key]
                if None in store:
                    return store[None]
            time.sleep(self._poll_interval)
        raise DeadlineExceededError(f"No {kind} received (key={key!r}) within {timeout}s")
