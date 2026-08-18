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

from ..policy.league_ledger import LeagueLedger
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
)
from .reporting import send_std_v1_report, write_std_v1_result, write_std_v1_sub_game_logs
from .scent_model_lock import build_scent_model_lock
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
    sub_games_to_play: int | None = None,
    counted: bool = False,
    league_ledger_path: str | None = None,
) -> dict:
    """Runs one full std_v1 series against `private_config.opponent_url`,
    writes the result JSON, and returns it. Raises `ValueError` up front
    if `opponent_group_id` (rule 6's own prerequisite — see
    `private_config.py`'s docstring) was never configured.

    `sub_games_to_play`: spec Section 15's own compatibility-test launch
    parameter, passed straight through to `play_series` — `None` (the
    default) plays the full signed series.

    `counted`/`league_ledger_path`: rule 52 (**[FATAL]**), enforced exactly
    as native — same `LeagueLedger`, keyed by `opponent_url`
    (`cli_peer_match_body.py`'s own convention), recorded once the series
    finishes regardless of outcome; `record_counted_game`'s own
    `ValueError` on a repeat opponent *is* the rule-52 gate, purely
    reactive like native. Every series also emails/draft-previews its own
    report (rule 34/35, unconditional on `counted`) — see
    `reporting.py::send_std_v1_report`."""
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
        kwargs={"transport": "http", "host": host, "port": private_config.my_port, "show_banner": False},
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
    # Rule-auditor cross-check against the real opponent's own interop
    # guide (spec Section 3/12, [REPORT]): this address is what the
    # opponent's own report records as *our* reachable endpoint — it must
    # be the real public tunnel URL, not the loopback address that's
    # useless to anyone outside this machine, whenever a tunnel is up.
    my_mcp_url = f"{tunnel.public_url}/mcp" if tunnel is not None else f"http://127.0.0.1:{private_config.my_port}/mcp"
    identity = build_identity(
        group_id=private_config.group_id,
        group_name=private_config.group_name,
        members=list(private_config.members),
        repos=private_config.repos,
        mcp_servers={"cop": my_mcp_url, "thief": my_mcp_url},
        llm_model=private_config.model,
        scent_model_lock=build_scent_model_lock(terms),
    )

    connection = PeerConnection(private_config.opponent_url)
    try:
        result = await play_series(
            connection, exchange, terms, private_config.group_id, private_config.opponent_group_id,
            identity, turn_handler_factory, thief_components_factory, config,
            turn_deadline_sec=private_config.turn_timeout_seconds,
            # I6: no fixed defaults for a real match — negotiate/audit
            # ceilings reuse the same "let a slower peer catch up" budgets
            # already negotiated for the native protocol's own Step-0 wait
            # and post-match grace period; the resend cadence reuses the
            # same shared retry-pacing field the connect-only retries below
            # already do, rather than a fifth set of numbers.
            resend_interval_sec=private_config.scent_map_retry_delay_seconds,
            negotiate_ceiling_sec=private_config.step0_wait_seconds,
            audit_ceiling_sec=private_config.post_match_grace_seconds,
            sub_games_to_play=sub_games_to_play,
            retry_attempts=private_config.scent_map_retry_attempts,
            retry_delay_seconds=private_config.scent_map_retry_delay_seconds,
        )
    finally:
        await connection.close()
        if tunnel is not None:
            stop_tunnel(tunnel)

    result_path = write_std_v1_result(result, results_dir)
    log_paths = write_std_v1_sub_game_logs(result, results_dir)

    if counted:
        ledger = LeagueLedger(path=league_ledger_path) if league_ledger_path else LeagueLedger()
        ledger.record_counted_game(private_config.opponent_url)

    send_std_v1_report(result, result_path, log_paths, private_config, config, results_dir)

    return result
