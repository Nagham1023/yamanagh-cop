"""Single entry point to every PRD 2/3 subsystem (rule 3).

Wires all five of the book's Orchestrator subsystems (Ch.8, Fig. 12): MCP
Connector (`tools/`), Log Manager (`observability/trace.py`), Deadline
Tracker, Watchdog, and — as of PRD 3 — the Decision Module (`reasoning/`).
Nothing outside this module reaches those subsystems directly.

The watchdog is doubly wired: every `receive_hint`/`share_scent_map` call
feeds it a heartbeat (via `self._on_connection_received`, wired as
`build_server`'s `on_receive`), and a daemon thread started in
`run_as_server` polls `watchdog.check()` so a frozen process actually gets
caught while serving, not just when a test calls `.check()` directly.

`take_turn()` is deliberately small — it proves the brain is genuinely
wired, not that the algorithm works. Algorithm correctness is
`reasoning/subgame.py`'s job, entirely offline (PRD-3-blind-strategy.md,
Design Question 3). `take_turn()` lives in `orchestrator_turn.py`'s
`BrainTurnMixin`; `run_as_server`/the watchdog poll loop live in
`orchestrator_server.py`'s `ServerLifecycleMixin`; `send_to_peer`/
`request_scent_map_from_peer`/the connection hook live in
`orchestrator_peer.py`'s `PeerCommsMixin` — this file grew past the
150-line house cap three times, once at each landing.
"""

from __future__ import annotations

import random

from fastmcp import FastMCP

from .domain.barriers import BarrierSet
from .domain.board import Board, Position
from .memory.belief import BeliefMap
from .memory.scent import ScentField
from .observability.trace import Trace
from .orchestrator_peer import PeerCommsMixin
from .orchestrator_server import ServerLifecycleMixin
from .orchestrator_turn import BrainTurnMixin
from .planner.state_machine import PeerStateMachine
from .planner.watchdog import Watchdog
from .reasoning.brain_base import BrainBase
from .reasoning.state import GameState
from .shared.config import GameConfig
from .shared.private_config import PrivateConfig
from .tools.hint_providers import TemplateHintProvider, build_provider
from .tools.mcp_server import build_server

_DEFAULT_PRIVATE_CONFIG_PATH = "config/game.toml"


class Orchestrator(BrainTurnMixin, PeerCommsMixin, ServerLifecycleMixin):
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
        barriers = BarrierSet(quota=config.barrier_quota)
        self.belief_map = BeliefMap.uniform(self.board, barriers=barriers)
        self.game_state = GameState(
            own_pos=Position(*config.cop_start),
            target_pos=self.belief_map.most_likely_cell(),
            barriers=barriers,
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
            config,
            on_receive=self._on_connection_received,
            on_hint=self._on_hint_received,
            get_scent_field=self.scent_field.full_field,
        )
