"""`run_std_v1_peer` — the whole std_v1 match, start to finish, for this
repo's Cop role. Selected by `[network] opponent_protocol = "std_v1"` in
`config/game.toml`, the same one-value-in-a-TOML-file switch
`private_config.py`'s own docstring describes. Deliberately a separate
entry point from `cli_peer.py::run_peer` rather than woven into
`Orchestrator`'s own fifteen-plus mixins: std_v1's match lifecycle
(per-sub-game negotiation, its own shared step counter, a final
series-consensus exchange, via `series_runner.py`) doesn't fit that
class's single-native-match shape, and grafting it in would risk the
watchdog/state-machine/gatekeeper machinery those mixins already carefully
coordinate. Runs its own dedicated `FastMCP` server on a background
thread (same shape as `orchestrator_server.py::run_as_server`) while the
async series runner drives the match on the caller's own event loop.
"""

from __future__ import annotations

import asyncio
import threading

from fastmcp import FastMCP

from ..reasoning.cop_brain import CopBrain
from ..shared.config import GameConfig
from ..shared.private_config import PrivateConfig
from ..shared.strategy_loader import load_brain_class
from ..tools.peer_connection import PeerConnection
from ..tools.tunnel import stop_tunnel
from ..tools.tunnel_start import start_tunnel
from .exchange import StdExchange
from .identity import build_identity
from .peer_setup import (
    build_std_v1_game_config,
    build_thief_components_factory,
    build_turn_handler_factory,
    write_std_v1_result,
)
from .series_runner import play_series
from .server_registration import register_std_v1_tools
from .terms import DEFAULT_TERMS_PATH, load_terms

_SERVER_STARTUP_GRACE_SECONDS = 0.5


async def run_std_v1_peer(
    private_config: PrivateConfig,
    base_config: GameConfig,
    terms_path: str = DEFAULT_TERMS_PATH,
    *,
    use_tunnel: bool = False,
    ngrok_domain: str | None = None,
    results_dir: str = "logs",
) -> dict:
    """Runs one full std_v1 series against `private_config.opponent_url`,
    writes the result JSON, and returns it. Raises `ValueError` up front
    if `opponent_group_id` (rule 6's own prerequisite — see
    `private_config.py`'s docstring) was never configured."""
    if not private_config.opponent_group_id:
        raise ValueError('[network] opponent_group_id is required when opponent_protocol = "std_v1"')

    terms = load_terms(terms_path)
    config = build_std_v1_game_config(base_config, terms)
    exchange = StdExchange()
    mcp = FastMCP(name="cop_peer_std_v1")
    register_std_v1_tools(mcp, exchange)

    host = "0.0.0.0" if use_tunnel else "127.0.0.1"
    threading.Thread(
        target=mcp.run,
        kwargs={
            "transport": "http", "host": host, "port": private_config.my_port, "show_banner": False,
        },
        daemon=True,
    ).start()
    tunnel = None
    if use_tunnel:
        tunnel = start_tunnel(private_config.my_port, domain=ngrok_domain, log_path="logs/ngrok_tunnel_std_v1.log")
        print(f"[tunnel] ngrok public URL: {tunnel.public_url}", flush=True)
    await asyncio.sleep(_SERVER_STARTUP_GRACE_SECONDS)

    brain_cls = load_brain_class(private_config.police_class) if private_config.police_class else CopBrain
    turn_handler_factory = build_turn_handler_factory(config, private_config, brain_cls)
    thief_components_factory = build_thief_components_factory(config)
    identity = build_identity(
        group_id=private_config.group_id,
        group_name=private_config.group_name,
        members=list(private_config.members),
        repos=private_config.repos,
        mcp_servers={
            "cop": f"http://127.0.0.1:{private_config.my_port}/mcp",
            "thief": f"http://127.0.0.1:{private_config.my_port}/mcp",
        },
        llm_model=private_config.model,
    )

    connection = PeerConnection(private_config.opponent_url)
    try:
        result = await play_series(
            connection, exchange, terms, private_config.group_id, private_config.opponent_group_id,
            identity, turn_handler_factory, thief_components_factory,
            turn_deadline_sec=private_config.turn_timeout_seconds,
        )
    finally:
        await connection.close()
        if tunnel is not None:
            stop_tunnel(tunnel)

    write_std_v1_result(result, results_dir)
    return result
