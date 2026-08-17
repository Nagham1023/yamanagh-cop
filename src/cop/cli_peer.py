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
    docstring has the full reasoning) that returns a plain result dict,
    not an `Orchestrator`, since `counted`/`--gui`/the league ledger are
    all native-protocol-only concerns std_v1 doesn't have."""
    del gui  # CLI routes --gui to run_peer_with_gui; kept for call-site compat
    private_config = PrivateConfig.from_file(private_config_path)
    if private_config.opponent_protocol == "std_v1":
        base_config = GameConfig.from_file(shared_config_path)
        return await run_std_v1_peer(private_config, base_config, use_tunnel=use_tunnel, ngrok_domain=ngrok_domain)

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
    async match runs in a background thread (Thief LiveSession pattern)."""
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
