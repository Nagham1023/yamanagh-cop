"""Single entry point to every PRD 2 subsystem (rule 3).

Wires four of the book's five Orchestrator subsystems (Ch.8, Fig. 12): MCP
Connector (`tools/`), Log Manager (`observability/trace.py`), Deadline
Tracker, Watchdog. The fifth, the Decision Module, is deliberately not
wired here — that's PRD 3's rule 25 and `BrainBase` contract (see
`PRD-2-fastmcp-infra.md`, Design Question 3). Nothing outside this module
reaches those four subsystems directly.

The watchdog is doubly wired: every `receive_position` call feeds it a
heartbeat (`build_server(..., on_receive=self.watchdog.heartbeat)`), and a
daemon thread started in `run_as_server` polls `watchdog.check()` so a
frozen process actually gets caught while serving, not just when a test
calls `.check()` directly.
"""

from __future__ import annotations

import os
import threading
import time

from fastmcp import FastMCP

from .observability.trace import Trace
from .planner.deadline import await_with_deadline
from .planner.state_machine import PeerStateMachine
from .planner.watchdog import Watchdog
from .shared.config import GameConfig
from .tools.mcp_client import send_position
from .tools.mcp_server import build_server


class Orchestrator:
    def __init__(self, config: GameConfig, log_path: str = "logs/trace.jsonl") -> None:
        self.config = config
        self.trace = Trace(log_path)
        self.state_machine = PeerStateMachine()
        self.watchdog = Watchdog(
            threshold_seconds=config.watchdog_threshold_seconds,
            persist_state=lambda: self.trace.log(
                "watchdog_persist_state", state=self.state_machine.state
            ),
            controlled_shutdown=lambda: self.trace.log(
                "watchdog_controlled_shutdown", state=self.state_machine.state
            ),
        )
        self.server: FastMCP = build_server(config, on_receive=self.watchdog.heartbeat)

    def _watch_loop(self, poll_interval_seconds: float) -> None:
        """Background daemon thread: rule 7 says "run" a watchdog, not merely
        construct one. `check()` already runs `persist_state`/`controlled_shutdown`
        on staleness; this loop's only remaining job is to end the frozen
        process once that has happened, so the OS-level crash/hang is real."""
        while True:
            time.sleep(poll_interval_seconds)
            if self.watchdog.check() == "SHUTDOWN":
                os._exit(1)

    def _start_watchdog_monitor(self, poll_interval_seconds: float = 1.0) -> None:
        threading.Thread(
            target=self._watch_loop, args=(poll_interval_seconds,), daemon=True
        ).start()

    def run_as_server(self, host: str = "127.0.0.1", port: int = 8800) -> None:
        """Start listening — blocking, meant to be this process's main loop."""
        self.trace.log("server_starting", host=host, port=port)
        self._start_watchdog_monitor()
        self.server.run(transport="http", host=host, port=port, show_banner=False)

    async def send_to_peer(self, peer_url: str, col: int, row: int) -> dict:
        """Client role: send a position to the peer, deadline-guarded, state-machine-tracked.

        On *any* failure to get a response — a deadline expiry, or the peer
        being gone entirely (connection refused/reset, e.g. a killed
        process) — this transitions to `TECHNICAL_LOSS`, logs why, and
        re-raises. A killed peer is caught by a live TCP handshake failing
        immediately, not by the timeout; only catching `DeadlineExceededError`
        here would leave the state machine stuck in `AWAITING_RESPONSE` and
        nothing logged for that case — exactly the "hang, not a clean loss"
        rule 6/7 exist to prevent. The caller decides what happens next;
        this method's job is only to make the loss real and recorded.
        """
        self.state_machine.transition("SENDING")
        self.trace.log("sending_position", peer_url=peer_url, col=col, row=row)

        self.state_machine.transition("AWAITING_RESPONSE")
        try:
            result = await await_with_deadline(
                send_position(peer_url, col, row),
                timeout_seconds=self.config.response_timeout_seconds,
            )
        except Exception as exc:
            self.trace.log(
                "technical_loss",
                reason=str(exc),
                exception_type=type(exc).__name__,
                state=self.state_machine.state,
            )
            self.state_machine.transition("TECHNICAL_LOSS")
            raise

        self.state_machine.transition("TURN_RESOLVED")
        self.trace.log("turn_resolved", result=result)
        self.state_machine.transition("WAITING_FOR_OPPONENT")
        return result
