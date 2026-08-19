"""Loopback-only relay endpoint exposing this repo's real police decision
machinery (`Std1TurnHandler`/`CopBrain`) to a separate `thief-peer` process
over the network — never a Python import, so the cop/thief process
separation `CLAUDE.md` rules 1/2 require stays intact even though this
side's real decisions now get used during a live cross-team match. Always
binds `127.0.0.1`, never tunneled — this is a same-team, same-machine
relay between this team's own two processes, not a peer-facing endpoint
(that role stays `peer.py::run_std_v1_peer`'s own tunneled server,
unaffected by anything in this file).

The move secret is sealed here, not by the caller: `decide_police_turn`
returns an already-committed `{payload, nonce, commit}`, so the real move
never exists inside the calling `thief-peer` process before it's revealed
at audit time (rule 18's own secrecy-until-game-end principle).
"""

from __future__ import annotations

from fastmcp import FastMCP

from ..reasoning.cop_brain import CopBrain
from ..shared.config import GameConfig
from ..shared.private_config import PrivateConfig
from ..shared.strategy_loader import load_brain_class
from .peer_setup import build_std_v1_game_config, build_turn_handler_factory
from .sealing import build_turn_payload, seal_turn
from .terms import DEFAULT_TERMS_PATH, load_terms
from .turn_handler import Std1TurnHandler

DEFAULT_RELAY_PORT = 8901


class _RelayState:
    """Holds the single active `Std1TurnHandler`. Sub-games are always
    relayed sequentially — the calling `thief-peer` process plays its own
    Thief-role sub-games entirely locally and only ever has one Police-role
    sub-game in flight at a time — so one slot is enough, no keying needed."""

    def __init__(self) -> None:
        self.handler: Std1TurnHandler | None = None
        self.sub_game_number: int | None = None


def register_relay_tools(mcp: FastMCP, turn_handler_factory, state: _RelayState) -> None:
    @mcp.tool
    def start_police_subgame(sub_game_number: int) -> dict:
        """Builds one fresh `Std1TurnHandler` for the given sub-game --
        mirrors `series_runner.py`'s own "one factory call per sub-game"
        lifecycle, just triggered by the relay client instead of this
        repo's own `play_series` loop."""
        state.handler = turn_handler_factory()
        state.sub_game_number = sub_game_number
        return {"ok": True}

    @mcp.tool
    def decide_police_turn(step: int, thief_smell_grid: dict, thief_hint_text: str) -> dict:
        """Runs one real turn of this repo's own police decision (belief
        update, `CopBrain` move, scent advance, hint generation --
        `Std1TurnHandler.play_turn`, unchanged), then seals it with this
        repo's own `sealing.py`. Raises if called before
        `start_police_subgame` -- a genuine caller bug, not a recoverable
        protocol condition."""
        if state.handler is None:
            raise RuntimeError("decide_police_turn called before start_police_subgame")
        decision = state.handler.play_turn(thief_smell_grid, thief_hint_text)
        payload = build_turn_payload(
            step=step,
            sender="police",
            move=decision["move"],
            hint=decision["hint"],
            smell_grid=decision["smell_grid"],
            barrier_placed=decision["barrier_placed"],
            capture_claim=decision["capture_claim"],
        )
        sealed = seal_turn(payload)
        return {"payload": payload, "nonce": sealed["nonce"], "commit": sealed["commit"]}


def run_cop_relay_server(
    private_config: PrivateConfig,
    base_config: GameConfig,
    terms_path: str = DEFAULT_TERMS_PATH,
    port: int = DEFAULT_RELAY_PORT,
) -> None:
    """Starts the loopback relay server and blocks forever. Intended entry
    point: `python -m cop relay` (see `__main__.py`), run as its own
    separate OS process alongside -- not instead of -- this team's normal
    `thief-peer` process for a match's whole duration."""
    terms = load_terms(terms_path)
    config = build_std_v1_game_config(base_config, terms)
    brain_cls = load_brain_class(private_config.police_class) if private_config.police_class else CopBrain
    turn_handler_factory = build_turn_handler_factory(config, private_config, brain_cls)

    state = _RelayState()
    mcp = FastMCP(name="cop_relay")
    register_relay_tools(mcp, turn_handler_factory, state)
    print(f"[relay] cop relay server listening on http://127.0.0.1:{port}/mcp (loopback only)", flush=True)
    mcp.run(transport="http", host="127.0.0.1", port=port, show_banner=False)
