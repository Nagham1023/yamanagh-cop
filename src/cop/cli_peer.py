"""`uv run python -m cop peer`'s real logic (CLAUDE.md/README.md's own
documented command, unbuilt until PRD 10 — PRD 7 explicitly deferred it).
`__main__.py` stays a thin argparse+dispatch wrapper; this module is the
independently testable core, callable directly (no argv needed) — the
same "logic in a plain function, CLI is just the caller" split every
other testable-CLI convention uses.

Sequence (see `_run_match_body`'s own docstring) is unconditional
regardless of `initiate_step0` — confirmed by reading
`orchestrator_turn.py::take_turn` before designing this: both sides always
drive their *own* turns, "initiator" only ever matters for Step-0.
`sub_game_scores`/`cumulative_score` are derived from
`domain/scoring.py::score_outcome` — the only honest source for a single
CLI-run match with no cross-game history to draw on.
"""

from __future__ import annotations

import asyncio
import threading

from .cli_peer_build import build_orchestrator
from .domain.scoring import score_outcome
from .observability.live_gui_session import LiveGuiSession
from .orchestrator import Orchestrator
from .shared.config import GameConfig
from .shared.private_config import PrivateConfig
from .shared.promotion_guard import require_fresh_promotion_report_for_counted_game

DEFAULT_PRIVATE_CONFIG_PATH = "config/game.toml"
DEFAULT_SHARED_CONFIG_PATH = "config/shared/config_dev_g01.json"
_SERVER_STARTUP_GRACE_SECONDS = 0.5


async def _run_match_body(
    orchestrator: Orchestrator,
    private_config: PrivateConfig,
    config: GameConfig,
    game_id: str,
    *,
    counted: bool,
    use_tunnel: bool,
) -> Orchestrator:
    """Server up, negotiate Step-0, play, report — the sequence both
    `run_peer` entry points share. PRD 13: refuses a counted game against
    `RLCopBrain` with no current promotion report, before the server
    thread even starts."""
    require_fresh_promotion_report_for_counted_game(orchestrator.brain, counted=counted)

    threading.Thread(
        target=orchestrator.run_as_server,
        kwargs={"port": private_config.my_port, "use_tunnel": use_tunnel},
        daemon=True,
    ).start()
    await asyncio.sleep(_SERVER_STARTUP_GRACE_SECONDS)

    peer_url = private_config.opponent_url
    if private_config.initiate_step0:
        await orchestrator.negotiate_step0(peer_url)
    else:
        await orchestrator.await_passive_step0(private_config.step0_wait_seconds)

    # GUI painting is owned by LiveGuiSession on the main thread — never by
    # play_game under asyncio (blank window on Windows).
    outcome = await orchestrator.play_game(peer_url, enable_gui=False)

    score = score_outcome(outcome, config)
    await orchestrator.report_game(
        peer_url,
        outcome,
        is_counted=counted,
        opponent_id=peer_url,
        sub_game_scores={game_id: score.cop},
        cumulative_score=score.cop,
    )
    return orchestrator


async def run_peer(
    private_config_path: str = DEFAULT_PRIVATE_CONFIG_PATH,
    shared_config_path: str = DEFAULT_SHARED_CONFIG_PATH,
    *,
    counted: bool = False,
    use_tunnel: bool = False,
    gui: bool = False,
    log_path: str | None = None,
    league_ledger_path: str | None = None,
) -> Orchestrator:
    """Runs one real match end to end. Returns the finished `Orchestrator`
    — its own `state_machine`/`log_path` are what a caller (or a test)
    inspects; `main()` itself doesn't need the return value. `log_path`/
    `league_ledger_path` default to this match's own real Table 20 name /
    `Orchestrator`'s own real default — overridable so tests never touch
    the real repo's `logs/` directory.

    Prefer `run_peer_with_gui` when `gui=True` — this async entry ignores
    the flag so callers that accidentally pass it still get a correct
    headless match rather than a blank Tk window under asyncio."""
    del gui  # CLI routes --gui to run_peer_with_gui; kept for call-site compat
    orchestrator, private_config, config, game_id = build_orchestrator(
        private_config_path,
        shared_config_path,
        log_path=log_path,
        league_ledger_path=league_ledger_path,
    )
    return await _run_match_body(
        orchestrator,
        private_config,
        config,
        game_id,
        counted=counted,
        use_tunnel=use_tunnel,
    )


def run_peer_with_gui(
    private_config_path: str = DEFAULT_PRIVATE_CONFIG_PATH,
    shared_config_path: str = DEFAULT_SHARED_CONFIG_PATH,
    *,
    counted: bool = False,
    use_tunnel: bool = False,
    log_path: str | None = None,
    league_ledger_path: str | None = None,
) -> Orchestrator:
    """Same match as `run_peer`, but Tk mainloop owns the main thread and the
    async match runs in a background thread (Thief LiveSession pattern)."""
    orchestrator, private_config, config, game_id = build_orchestrator(
        private_config_path,
        shared_config_path,
        log_path=log_path,
        league_ledger_path=league_ledger_path,
    )

    def match_fn() -> Orchestrator:
        """Synchronous wrapper `LiveGuiSession.run` calls from Tk's own thread."""
        return asyncio.run(
            _run_match_body(
                orchestrator,
                private_config,
                config,
                game_id,
                counted=counted,
                use_tunnel=use_tunnel,
            )
        )

    LiveGuiSession(orchestrator, board_size=config.board_size).run(match_fn)
    return orchestrator
