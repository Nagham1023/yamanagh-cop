"""`build_orchestrator`, split out of `cli_peer.py` to stay under the
150-line cap once PRD 13's `police_class` wiring landed there (CLAUDE.md's
"extract a shared helper into its own file" split strategy)."""

from __future__ import annotations

from .orchestrator import Orchestrator
from .policy.league_ledger import LeagueLedger
from .reasoning.cop_brain import CopBrain
from .shared.config import GameConfig
from .shared.private_config import PrivateConfig
from .shared.strategy_loader import load_brain_class
from .tools.report_bundle import log_filename


def build_orchestrator(
    private_config_path: str,
    shared_config_path: str,
    *,
    log_path: str | None = None,
    league_ledger_path: str | None = None,
) -> tuple[Orchestrator, PrivateConfig, GameConfig, str]:
    """Loads both config files and constructs one real `Orchestrator`,
    ready to run a match — `run_peer`/`run_peer_with_gui` are the only
    real callers; tests call it directly to inspect the result without
    starting a server."""
    private_config = PrivateConfig.from_file(private_config_path)
    config = GameConfig.from_file(shared_config_path)
    game_id = f"{private_config.group_id}_g{private_config.sub_game_number:02d}"
    if log_path is None:
        # log_filename appends its own "_g{NN}" from sub_game_number — the
        # bare group_id, not the already-suffixed game_id (report_game()'s
        # own docstring has the full story; found by literally running
        # `uv run python -m cop peer`, not by any unit test).
        log_path = f"logs/{log_filename(private_config.group_id, private_config.sub_game_number)}"

    # PRD 13: police_class, parsed since PRD 4, is finally consumed here.
    # CopBrain stays the real default while it's unset — a later, separate,
    # explicitly human-approved commit is what would ever flip that default
    # (see PRD-13-ml-pipeline-and-deployment.md's Design Question 1).
    brain_cls = load_brain_class(private_config.police_class) if private_config.police_class else CopBrain
    orchestrator = Orchestrator(
        config,
        brain_cls(),
        log_path=log_path,
        private_config=private_config,
        shared_config_path=shared_config_path,
    )
    if league_ledger_path is not None:
        orchestrator.league_ledger = LeagueLedger(path=league_ledger_path)
    return orchestrator, private_config, config, game_id
