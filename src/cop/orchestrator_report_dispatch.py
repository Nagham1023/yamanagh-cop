"""The rest of `report_game()`'s body — split out of `orchestrator_end_of_game.py`
once wrapping it in a failure-logging `try/except` (the fix for a real gap: this
whole tail used to have zero exception handling, so a `ValueError` from a missing
Step-0 declaration, a `KeyError` from the shared config, a file-write error, or a
Gatekeeper/Gmail rejection all propagated completely unlogged out of the entire
match pipeline) would have pushed the original file past the 150-line house cap.
`EndOfGameMixin.report_game` is the only caller.
"""

from __future__ import annotations

import json
from pathlib import Path

from .domain.scoring import Outcome, Score
from .integrity.audit import run_mutual_audit
from .tools.gmail_sender import get_service, send_report_bundle
from .tools.report_bundle import (
    DeclarationBundle,
    build_declaration,
    config_filename,
    declaration_filename,
    load_config_dict,
    load_log_entries,
    log_filename,
    result_filename,
)
from .tools.report_bundle_series import merge_into_series_result


class ReportDispatchMixin:
    async def _finish_report_game(
        self,
        outcome: Outcome,
        is_counted: bool,
        opponent_id: str,
        score: Score,
        opponent_cop_repo_url: str | None,
        opponent_thief_repo_url: str | None,
    ) -> dict | None:
        """Everything in `report_game()` past the Final Reveal send: mutual
        audit, sub-game-entry build, series-result merge/write, and — only
        on the series' last sub-game — the declaration write and Gatekeeper/
        Gmail dispatch. Unchanged in behavior from before the split; the
        caller now wraps this whole call in one failure-logging try/except
        instead of it having none at all."""
        await self._await_peer_final_reveal()
        self_audit = run_mutual_audit(self.log_path, self._pending_nonces)
        peer_audit = self.audit_peer()

        first_meeting = not self.league_ledger.is_already_counted(opponent_id)
        if is_counted:
            self.league_ledger.record_counted_game(opponent_id)

        entry = self._build_sub_game_entry(outcome, score, self_audit.passed, peer_audit.passed, is_counted)
        game_id = self.private_config.group_id
        raw_config = load_config_dict(self.shared_config_path)
        num_sub_games = raw_config["network_and_league"]["num_games"]
        repo_urls = {
            entry.this_group + "_cop": self.private_config.repos["cop"],
            entry.this_group + "_thief": self.private_config.repos["thief"],
            entry.opponent_group + "_cop": opponent_cop_repo_url,
            entry.opponent_group + "_thief": opponent_thief_repo_url,
        }

        reports_dir = Path(self.log_path).parent
        result_path = reports_dir / result_filename(game_id)
        previous = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else None
        result_payload = merge_into_series_result(
            previous,
            entry,
            game_id=game_id,
            num_sub_games=num_sub_games,
            games_played_including_this=self.league_ledger.counted_game_count(),
            first_meeting_between_groups=first_meeting,
            repo_urls=repo_urls,
            declaration_file=declaration_filename(game_id),
            tie_score=self.config.score_draw,
        )
        reports_dir.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result_payload, sort_keys=True), encoding="utf-8")

        if entry.sub_game_number < num_sub_games:
            # ch. 9.4: the report is for the whole series, sent once — see
            # module docstring. This sub-game's own files are already real,
            # on disk; only the Gatekeeper/email dispatch waits.
            self.trace.log(
                "sub_game_result_persisted_awaiting_series_completion",
                sub_game_number=entry.sub_game_number,
                num_sub_games=num_sub_games,
            )
            return None

        declaration_payload = build_declaration(
            DeclarationBundle(
                step0=self._build_own_step0(),
                group_name=self.private_config.group_name,
                members=self.private_config.members,
                cop_repo_url=self.private_config.repos["cop"],
                thief_repo_url=self.private_config.repos["thief"],
                token_budget_per_series=self.config.token_budget_per_series,
                started_at=self._match_started_at,
                ended_at=self._match_ended_at,
            )
        )
        (reports_dir / declaration_filename(game_id)).write_text(
            json.dumps(declaration_payload, sort_keys=True), encoding="utf-8"
        )

        sub_game_number = self.private_config.sub_game_number
        attachments = {
            declaration_filename(game_id): declaration_payload,
            config_filename(game_id, sub_game_number): raw_config,
            log_filename(game_id, sub_game_number): load_log_entries(self.log_path),
            result_filename(game_id): result_payload,
        }

        email_mode = self.private_config.email_mode
        # `send_report_bundle` never touches `service` at all under
        # "draft" — skip `get_service()` (a real token.json, unavailable
        # in this environment) entirely rather than pay a cost this call
        # path was never going to need.
        service = None if email_mode == "draft" else get_service()
        subject_id = f"{game_id}_g{sub_game_number:02d}"  # human-readable only — not a Table 20 filename
        return self.gatekeeper.execute(
            send_report_bundle,
            service,
            self.private_config.email_recipient,
            f"Match result — {subject_id}",
            f"Outcome: {outcome.value}",
            attachments,
            email_mode=email_mode,
            draft_dir=reports_dir,
        )
