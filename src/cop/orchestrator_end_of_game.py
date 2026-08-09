"""PRD 8's automatic end-of-game sequence (rules 32, 36) — the second real
gap `rule-auditor`'s PRD 7 closing-pass review found: every piece
(`run_mutual_audit`, `audit_peer`, `report_bundle.py`, `gmail_sender.py`,
`ApiGatekeeper`) was correct and tested in isolation, but nothing called
them together, in order, when a game actually ends.

`opponent_cop_repo_url`/`opponent_thief_repo_url` default to `None`,
sourced from `self._opponent_repos` (PRD 9's `negotiate_step0`) when
omitted — explicit params stay, for a caller that needs to override.
`sub_game_scores`/`cumulative_score`/`is_counted` stay caller-supplied,
not derived: cross-sub-game state spans more than one `Orchestrator`
lifetime (PRD 6's own I1 invariant), genuinely external data.

PRD 10: all four Table 20 files are attached (previously only `result_`).
`self.shared_config_path`/`self.log_path` supply `config_`/`log_`;
`self._match_started_at`/`_match_ended_at` (`orchestrator_game_loop.py`)
fill the declaration's last fields. `game_id` below is the bare Table 20
token (`PARAMETERS.md`: "file names derive from `game_id` and sub-game
number `<NN>`" — two independent axes): `declaration_`/`result_` take
only `game_id` (no `<NN>` — one evolving pair of files per series,
`ResultBundle.sub_game_scores` accumulates per-sub-game data inside
them); `config_`/`log_` take `game_id` *and* `sub_game_number`
separately, appending their own `_g{NN}`. `rule-auditor` found this
inconsistent in the first draft (`declaration_`/`result_` got the
already-suffixed string) — fixed at both call sites here.
"""

from __future__ import annotations

from .domain.scoring import Outcome
from .integrity.audit import run_mutual_audit
from .integrity.step0 import current_git_commit_hash
from .observability.cost import aggregate_tokens
from .tools.gmail_sender import get_service, send_report_bundle
from .tools.report_bundle import (
    DeclarationBundle,
    ResultBundle,
    build_declaration,
    build_result,
    config_filename,
    declaration_filename,
    load_config_dict,
    load_log_entries,
    log_filename,
    result_filename,
)


class EndOfGameMixin:
    def _opponent_repo_url(self, role: str) -> str:
        if self._opponent_repos is None:
            raise ValueError(
                f"opponent_{role}_repo_url was not supplied and no Step-0 "
                f"negotiation has completed (self._opponent_repos is None) "
                f"— call negotiate_step0() first, or pass it explicitly."
            )
        return self._opponent_repos[role]

    async def report_game(
        self,
        peer_url: str,
        outcome: Outcome,
        is_counted: bool,
        opponent_id: str,
        sub_game_scores: dict[str, int],
        cumulative_score: int,
        opponent_cop_repo_url: str | None = None,
        opponent_thief_repo_url: str | None = None,
    ) -> dict | None:
        """Design Question 4: separate from `play_game()` itself, called
        once by a thin caller after the loop returns — a test proving
        `play_game()` reaches the right `Outcome` shouldn't also need a
        working `ApiGatekeeper`/Gmail mock, and vice versa. Design
        Question 5: `is_counted` is the caller's own policy decision
        (`league_ledger`'s job to enforce, not this method's to re-derive).

        Rule 49: `opponent_cop_repo_url`/`opponent_thief_repo_url` fall
        back to `self._opponent_repos` (set by a completed Step-0
        negotiation, `orchestrator_step0.py`) when not explicitly passed.
        Raises `ValueError` — never silently emits an empty string into an
        audit-relevant JSON field — if neither source is available.
        """
        opponent_cop_repo_url = opponent_cop_repo_url or self._opponent_repo_url("cop")
        opponent_thief_repo_url = opponent_thief_repo_url or self._opponent_repo_url("thief")
        try:
            await self.send_final_reveal_to_peer(peer_url)
        except Exception as exc:
            self.trace.log("final_reveal_send_failed", error=str(exc))

        self_audit = run_mutual_audit(self.log_path, self._pending_nonces)
        peer_audit = self.audit_peer()

        if is_counted:
            self.league_ledger.record_counted_game(opponent_id)

        totals = aggregate_tokens(self.log_path)
        result_bundle = ResultBundle(
            sub_game_scores=sub_game_scores,
            cumulative_score=cumulative_score,
            code_commit_hash=current_git_commit_hash(),
            total_tokens=totals.total_tokens,
            cop_repo_url=self.private_config.repos["cop"],
            thief_repo_url=self.private_config.repos["thief"],
            opponent_cop_repo_url=opponent_cop_repo_url,
            opponent_thief_repo_url=opponent_thief_repo_url,
            self_audit_passed=self_audit.passed,
            peer_audit_passed=peer_audit.passed,
        )
        declaration_bundle = DeclarationBundle(
            step0=self._build_own_step0(),
            group_name=self.private_config.group_name,
            members=self.private_config.members,
            cop_repo_url=self.private_config.repos["cop"],
            thief_repo_url=self.private_config.repos["thief"],
            token_budget_per_series=self.config.token_budget_per_series,
            started_at=self._match_started_at,
            ended_at=self._match_ended_at,
        )

        sub_game_number = self.private_config.sub_game_number
        game_id = self.private_config.group_id  # bare Table 20 token — see module docstring
        attachments = {
            declaration_filename(game_id): build_declaration(declaration_bundle),
            config_filename(game_id, sub_game_number): load_config_dict(self.shared_config_path),
            log_filename(game_id, sub_game_number): load_log_entries(self.log_path),
            result_filename(game_id): build_result(result_bundle),
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
        )
