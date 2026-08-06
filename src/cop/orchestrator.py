"""Single entry point to every PRD 2/3 subsystem (rule 3).

Wires all five of the book's Orchestrator subsystems (Ch.8, Fig. 12): MCP
Connector (`tools/`), Log Manager (`observability/trace.py`), Deadline
Tracker, Watchdog, and — as of PRD 3 — the Decision Module (`reasoning/`).
Nothing outside this module reaches those subsystems directly.

The watchdog is doubly wired: every `receive_hint` call feeds it a
heartbeat (`build_server(..., on_receive=self.watchdog.heartbeat)`), and a
daemon thread started in `run_as_server` polls `watchdog.check()` so a
frozen process actually gets caught while serving, not just when a test
calls `.check()` directly.

`take_turn()` is deliberately small — it proves the brain is genuinely
wired, not that the algorithm works. Algorithm correctness is
`reasoning/subgame.py`'s job, entirely offline (PRD-3-blind-strategy.md,
Design Question 3). `take_turn()` itself lives in `orchestrator_turn.py`'s
`BrainTurnMixin` — this file grew past the 150-line house cap once that
method landed.
"""

from __future__ import annotations

import os
import random
import threading
import time

from fastmcp import FastMCP

from .domain.barriers import BarrierSet
from .domain.board import Board, Position
from .memory.belief import BeliefMap
from .memory.scent import ScentField
from .observability.trace import Trace
from .orchestrator_turn import BrainTurnMixin
from .planner.deadline import await_with_deadline
from .planner.state_machine import PeerStateMachine
from .planner.watchdog import Watchdog
from .reasoning.brain_base import BrainBase
from .reasoning.state import GameState
from .shared.config import GameConfig
from .shared.private_config import PrivateConfig
from .tools.hint_providers import TemplateHintProvider, build_provider
from .tools.mcp_client import send_hint
from .tools.mcp_server import build_server

_DEFAULT_PRIVATE_CONFIG_PATH = "config/private/trash_talk_dev.json"


class Orchestrator(BrainTurnMixin):
    def __init__(
        self,
        config: GameConfig,
        brain: BrainBase,
        log_path: str = "logs/trace.jsonl",
        private_config: PrivateConfig | None = None,
    ) -> None:
        self.config = config
        self.brain = brain
        self.board = Board(size=config.board_size)
        self.scent_field = ScentField.from_config(config)
        self.belief_map = BeliefMap.uniform(self.board)
        self.game_state = GameState(
            own_pos=Position(*config.cop_start),
            target_pos=self.belief_map.most_likely_cell(),
            barriers=BarrierSet(quota=config.barrier_quota),
        )
        self.private_config = private_config or PrivateConfig.from_file(_DEFAULT_PRIVATE_CONFIG_PATH)
        self.hint_provider = build_provider(self.private_config.provider)
        self.template_provider = TemplateHintProvider()
        self._rng = random.Random()
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
        self.server: FastMCP = build_server(
            config, on_receive=self.watchdog.heartbeat, on_hint=self._on_hint_received
        )

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

    async def send_to_peer(self, peer_url: str, text: str) -> dict:
        """Client role: send a natural-language hint to the peer, deadline-guarded,
        state-machine-tracked (rule 26/27 — no coordinates, ever, past this point).

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
        self.trace.log("sending_hint", peer_url=peer_url, text=text)

        self.state_machine.transition("AWAITING_RESPONSE")
        try:
            result = await await_with_deadline(
                send_hint(peer_url, text),
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
