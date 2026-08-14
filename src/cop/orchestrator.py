"""Single entry point to every PRD 2/3 subsystem (rule 3).

Wires all five of the book's Orchestrator subsystems (Ch.8, Fig. 12): MCP
Connector (`tools/`), Log Manager (`observability/trace.py`), Deadline
Tracker, Watchdog, and — as of PRD 3 — the Decision Module (`reasoning/`).
Nothing outside this module reaches those subsystems directly.

Watchdog: every tool call feeds it a heartbeat (`on_receive`), and a
daemon thread in `run_as_server` polls `watchdog.check()` so a frozen
process gets caught while serving. Turns/reveals/Commit-Reveal live in
`orchestrator_turn.py`/`orchestrator_reveal_received.py`/
`orchestrator_commit_reveal.py` — split again each cap re-hit.
"""

from __future__ import annotations

import asyncio
import random
import threading

from fastmcp import FastMCP

from .domain.barriers import BarrierSet
from .domain.board import Board, Position
from .integrity.capture_protocol import CaptureResponse
from .integrity.peer_trace import PeerTrace
from .integrity.step0 import Step0Declaration
from .memory.belief import BeliefMap
from .memory.scent import ScentField
from .observability.trace import Trace
from .orchestrator_capture import CaptureClaimMixin
from .orchestrator_commit_reveal import CommitRevealMixin
from .orchestrator_end_of_game import EndOfGameMixin
from .orchestrator_game_loop import GameLoopMixin
from .orchestrator_peer import PeerCommsMixin
from .orchestrator_peer_audit import PeerAuditMixin
from .orchestrator_peer_commit import PeerCommitMixin
from .orchestrator_report_entry import ReportEntryMixin
from .orchestrator_reveal_received import RevealReceivedMixin
from .orchestrator_server import ServerLifecycleMixin
from .orchestrator_step0 import Step0NegotiationMixin
from .orchestrator_step0_wait import Step0PassiveWaitMixin
from .orchestrator_turn import BrainTurnMixin
from .planner.state_machine import PeerStateMachine
from .planner.watchdog import Watchdog
from .policy.gatekeeper import ApiGatekeeper
from .policy.league_ledger import LeagueLedger
from .reasoning.brain_base import BrainBase
from .reasoning.state import GameState
from .shared.config import GameConfig
from .shared.private_config import PrivateConfig
from .tools.hint_providers import TemplateHintProvider, build_provider
from .tools.mcp_server import build_server

_DEFAULT_PRIVATE_CONFIG_PATH = "config/game.toml"
_DEFAULT_SHARED_CONFIG_PATH = "config/shared/config_dev_g01.json"  # negotiate_step0's re-hash target


class Orchestrator(
    BrainTurnMixin,
    CaptureClaimMixin,
    CommitRevealMixin,
    EndOfGameMixin,
    GameLoopMixin,
    PeerCommsMixin,
    PeerAuditMixin,
    PeerCommitMixin,
    ReportEntryMixin,
    RevealReceivedMixin,
    ServerLifecycleMixin,
    Step0NegotiationMixin,
    Step0PassiveWaitMixin,
):
    def __init__(
        self,
        config: GameConfig,
        brain: BrainBase,
        log_path: str = "logs/trace.jsonl",
        private_config: PrivateConfig | None = None,
        shared_config_path: str = _DEFAULT_SHARED_CONFIG_PATH,
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
        self.shared_config_path = shared_config_path  # PRD 9: negotiate_step0's own re-hash target
        self.hint_provider = build_provider(self.private_config.provider)
        self.template_provider = TemplateHintProvider()
        self._rng = random.Random()
        self.trace = Trace(log_path)
        self.log_path = log_path  # report_game() hands this to run_mutual_audit (Trace's own path is private)
        self.league_ledger = LeagueLedger()
        self.gatekeeper = ApiGatekeeper(config)
        self.state_machine = PeerStateMachine()
        # Rule 18: this side's own nonces, never sent until receive_final_reveal, keyed by step.
        self._pending_nonces: dict[int, str] = {}
        self._pending_intents: dict[int, bool] = {}  # same lifetime/reason as _pending_nonces
        self.peer_trace = PeerTrace()  # peer's committed/revealed data — run_peer_audit verifies against this (19/36)
        self._init_cross_thread_signals()
        self._last_turn_captured = False
        self._last_hint_received: str | None = None  # PRD 7 round-2: live-GUI display only
        self._peer_final_reveal_received = False  # ch.5.3.2 step 4; set from the MCP server thread, play_game reads it
        # Filled in by negotiate_step0/_on_step0_received — report_game (rule 49) sources repo URLs from here.
        self._opponent_repos: dict[str, str] | None = None
        self._opponent_declaration: Step0Declaration | None = None  # PRD 16: group_name/code_commit_hash
        self._step0_completed: bool = False  # set once by _signal_step0_received
        self._match_started_at: str | None = None  # set by play_game() — report_game() needs both
        self._match_ended_at: str | None = None
        self.watchdog = Watchdog(
            threshold_seconds=config.watchdog_threshold_seconds,
            persist_state=self._persist_watchdog_state,
            controlled_shutdown=lambda: self.trace.log(
                "watchdog_controlled_shutdown", state=self.state_machine.state
            ),
        )
        self.server: FastMCP = build_server(
            config,
            on_receive=self._on_connection_received,
            get_scent_field=self._get_and_commit_scent_field,
            on_reveal=self._on_reveal_received,
            on_commit=self._on_commit_received,
            on_final_reveal=self._on_final_reveal_received,
            on_capture_claim=self._on_capture_claim_received,
            on_capture_response=self._on_capture_response_received,
            on_step0=self._on_step0_received,
        )

    def _init_cross_thread_signals(self) -> None:
        """Event/loop pairs `orchestrator_capture.py`/`orchestrator_step0_wait.py`/
        `orchestrator_peer_audit.py` use to hand a result from the MCP server
        thread back to an awaiting asyncio loop."""
        self._capture_response_event = asyncio.Event()
        self._capture_response: CaptureResponse | None = None
        self._capture_response_loop: asyncio.AbstractEventLoop | None = None
        self._step0_received_event = asyncio.Event()
        self._step0_received_loop: asyncio.AbstractEventLoop | None = None
        self._step0_failure: Exception | None = None
        self._peer_final_reveal_event = asyncio.Event()
        self._peer_final_reveal_loop: asyncio.AbstractEventLoop | None = None
        self._watchdog_stop_event = threading.Event()  # plain thread, not asyncio (orchestrator_server.py)
