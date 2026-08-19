"""`uv run python -m cop peer`'s real logic (CLAUDE.md/README.md's own
documented command, unbuilt until PRD 10 — PRD 7 explicitly deferred it).
`__main__.py` stays a thin argparse+dispatch wrapper; this module is the
independently testable core, callable directly (no argv needed) — the
same "logic in a plain function, CLI is just the caller" split every
other testable-CLI convention uses.

Sequence (see `cli_peer_match_body.py::run_match_body`'s own docstring,
split out separately once it grew past the 150-line house cap) is
unconditional regardless of `initiate_step0`.
"""

from __future__ import annotations

import asyncio

from .cli_peer_build import build_orchestrator
from .cli_peer_match_body import run_match_body
from .observability.live_gui_session import LiveGuiSession
from .orchestrator import Orchestrator
from .shared.config import GameConfig
from .shared.private_config import PrivateConfig
from .std_v1.peer import run_std_v1_peer
from .std_v1.relay_server import DEFAULT_RELAY_PORT, run_cop_relay_server

DEFAULT_PRIVATE_CONFIG_PATH = "config/game.toml"
DEFAULT_SHARED_CONFIG_PATH = "config/shared/config_dev_g01.json"


async def run_peer(
    private_config_path: str = DEFAULT_PRIVATE_CONFIG_PATH,
    shared_config_path: str = DEFAULT_SHARED_CONFIG_PATH,
    *,
    counted: bool = False,
    use_tunnel: bool = False,
    ngrok_domain: str | None = None,
    tunnel_provider: str = "ngrok",
    gui: bool = False,
    log_path: str | None = None,
    league_ledger_path: str | None = None,
    std_v1_sub_games: int | None = None,
) -> Orchestrator | dict:
    """Runs one real match end to end. Returns the finished `Orchestrator`
    — its own `state_machine`/`log_path` are what a caller (or a test)
    inspects; `main()` itself doesn't need the return value. `log_path`/
    `league_ledger_path` default to this match's own real Table 20 name /
    `Orchestrator`'s own real default — overridable so tests never touch
    the real repo's `logs/` directory.

    Prefer `run_peer_with_gui` when `gui=True` — this async entry ignores
    the flag so callers that accidentally pass it still get a correct
    headless match rather than a blank Tk window under asyncio.

    `[network] opponent_protocol = "std_v1"` (checked before any
    `Orchestrator` is built) short-circuits to `run_std_v1_peer` instead —
    a genuinely different match lifecycle (`std_v1/peer.py`'s own
    docstring has the full reasoning) that returns a plain result dict, not
    an `Orchestrator`. `counted`/`league_ledger_path` thread straight
    through to `run_std_v1_peer`'s own rule-52 enforcement (same
    `LeagueLedger`, same `opponent_url` key as the native path) — only
    `--gui` is a genuine native-protocol-only concern (std_v1 has no GUI at
    all; `run_peer_with_gui` rejects that combination itself).
    `std_v1_sub_games` is std_v1-only too — spec Section 15's
    compatibility-test launch parameter, ignored on the native path."""
    del gui  # CLI routes --gui to run_peer_with_gui; kept for call-site compat
    private_config = PrivateConfig.from_file(private_config_path)
    if private_config.opponent_protocol == "std_v1":
        base_config = GameConfig.from_file(shared_config_path)
        return await run_std_v1_peer(
            private_config, base_config, use_tunnel=use_tunnel, ngrok_domain=ngrok_domain,
            tunnel_provider=tunnel_provider, sub_games_to_play=std_v1_sub_games,
            counted=counted, league_ledger_path=league_ledger_path,
        )

    orchestrator, private_config, config, _game_id = build_orchestrator(
        private_config_path,
        shared_config_path,
        log_path=log_path,
        league_ledger_path=league_ledger_path,
    )
    return await run_match_body(
        orchestrator,
        private_config,
        config,
        counted=counted,
        use_tunnel=use_tunnel,
        ngrok_domain=ngrok_domain,
        tunnel_provider=tunnel_provider,
    )


def run_cop_relay(
    private_config_path: str = DEFAULT_PRIVATE_CONFIG_PATH,
    shared_config_path: str = DEFAULT_SHARED_CONFIG_PATH,
    *,
    port: int = DEFAULT_RELAY_PORT,
) -> None:
    """Runs this repo's loopback-only police-decision relay -- see
    `std_v1/relay_server.py`'s own docstring for why this exists and what
    it does and doesn't expose. Blocks forever; stop with Ctrl+C. A
    separate process from `run_peer`, started independently and left
    running for a match's whole duration."""
    private_config = PrivateConfig.from_file(private_config_path)
    base_config = GameConfig.from_file(shared_config_path)
    run_cop_relay_server(private_config, base_config, port=port)


def run_peer_with_gui(
    private_config_path: str = DEFAULT_PRIVATE_CONFIG_PATH,
    shared_config_path: str = DEFAULT_SHARED_CONFIG_PATH,
    *,
    counted: bool = False,
    use_tunnel: bool = False,
    ngrok_domain: str | None = None,
    tunnel_provider: str = "ngrok",
    log_path: str | None = None,
    league_ledger_path: str | None = None,
) -> Orchestrator:
    """Same match as `run_peer`, but Tk mainloop owns the main thread and the
    async match runs in a background thread (Thief LiveSession pattern).

    Rejects `[network] opponent_protocol = "std_v1"` up front, before
    `build_orchestrator` ever runs — std_v1 has no GUI anywhere in its own
    package (a permanent scope limit, not a deferred TODO), so silently
    falling through to a native match here would run the wrong protocol
    against a std_v1-configured opponent with no error at all."""
    private_config = PrivateConfig.from_file(private_config_path)
    if private_config.opponent_protocol == "std_v1":
        raise ValueError(
            '--gui is not supported when [network] opponent_protocol = "std_v1" '
            "(std_v1 has no GUI) — omit --gui to run the std_v1 match headless"
        )

    orchestrator, private_config, config, _game_id = build_orchestrator(
        private_config_path,
        shared_config_path,
        log_path=log_path,
        league_ledger_path=league_ledger_path,
    )

    def match_fn() -> Orchestrator:
        """Synchronous wrapper `LiveGuiSession.run` calls from Tk's own thread."""
        return asyncio.run(
            run_match_body(
                orchestrator,
                private_config,
                config,
                counted=counted,
                use_tunnel=use_tunnel,
                ngrok_domain=ngrok_domain,
                tunnel_provider=tunnel_provider,
            )
        )

    LiveGuiSession(orchestrator, board_size=config.board_size).run(match_fn)
    return orchestrator
