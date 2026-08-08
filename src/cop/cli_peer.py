"""`uv run python -m cop peer`'s real logic (CLAUDE.md/README.md's own
documented command, unbuilt until PRD 10 — PRD 7 explicitly deferred it).
`__main__.py` stays a thin argparse+dispatch wrapper; this module is the
independently testable core, callable directly (no argv needed) — the
same "logic in a plain function, CLI is just the caller" split every
other testable-CLI convention uses.

Sequence, unconditional regardless of `initiate_step0` (confirmed by
reading `orchestrator_turn.py::take_turn` before designing this: both
sides always drive their *own* turns — "initiator" only ever matters for
Step-0, not for who "goes first" in the match): construct `Orchestrator`
→ start `run_as_server` in a background thread → negotiate Step-0 (as
initiator or passively, per `[network].initiate_step0`) → `play_game` →
`report_game`. `sub_game_scores`/`cumulative_score` are derived from
`domain/scoring.py::score_outcome` (already built, reused) — the only
honest source for a single CLI-run match with no cross-game history to
draw on.
"""

from __future__ import annotations

import asyncio
import threading

from .domain.scoring import score_outcome
from .orchestrator import Orchestrator
from .policy.league_ledger import LeagueLedger
from .reasoning.cop_brain import CopBrain
from .shared.config import GameConfig
from .shared.private_config import PrivateConfig
from .tools.report_bundle import log_filename

DEFAULT_PRIVATE_CONFIG_PATH = "config/game.toml"
DEFAULT_SHARED_CONFIG_PATH = "config/shared/config_dev_g01.json"
_SERVER_STARTUP_GRACE_SECONDS = 0.5


async def run_peer(
    private_config_path: str = DEFAULT_PRIVATE_CONFIG_PATH,
    shared_config_path: str = DEFAULT_SHARED_CONFIG_PATH,
    *,
    counted: bool = False,
    use_tunnel: bool = False,
    log_path: str | None = None,
    league_ledger_path: str | None = None,
) -> Orchestrator:
    """Runs one real match end to end. Returns the finished `Orchestrator`
    — its own `state_machine`/`log_path` are what a caller (or a test)
    inspects; `main()` itself doesn't need the return value. `log_path`/
    `league_ledger_path` default to this match's own real Table 20 name /
    `Orchestrator`'s own real default — overridable so tests never touch
    the real repo's `logs/` directory."""
    private_config = PrivateConfig.from_file(private_config_path)
    config = GameConfig.from_file(shared_config_path)
    game_id = f"{private_config.group_id}_g{private_config.sub_game_number:02d}"
    if log_path is None:
        # log_filename appends its own "_g{NN}" from sub_game_number — the
        # bare group_id, not the already-suffixed game_id (report_game()'s
        # own docstring has the full story; found by literally running
        # `uv run python -m cop peer`, not by any unit test).
        log_path = f"logs/{log_filename(private_config.group_id, private_config.sub_game_number)}"

    orchestrator = Orchestrator(
        config,
        CopBrain(),
        log_path=log_path,
        private_config=private_config,
        shared_config_path=shared_config_path,
    )
    if league_ledger_path is not None:
        orchestrator.league_ledger = LeagueLedger(path=league_ledger_path)

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

    outcome = await orchestrator.play_game(peer_url)

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
