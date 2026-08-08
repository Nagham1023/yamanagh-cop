"""PRD 8's automatic end-of-game sequence (rules 32, 36) — the second real
gap `rule-auditor`'s PRD 7 closing-pass review found: every piece
(`run_mutual_audit`, `audit_peer`, `report_bundle.py`, `gmail_sender.py`,
`ApiGatekeeper`) was correct and tested in isolation, but nothing called
them together, in order, when a game actually ends.

`opponent_cop_repo_url`/`opponent_thief_repo_url` now default to `None` and
are sourced from `self._opponent_repos` (PRD 9's `negotiate_step0`/
`_on_step0_received`, `orchestrator_step0.py`) when omitted — closes the
gap this module's own docstring used to flag here: "this repo has no
channel anywhere for learning the opponent's own repo URLs." The explicit
parameters stay, for a caller that genuinely needs to override (a test, or
a real match where negotiation ran against a different peer than the one
`report_game` is reporting against). `sub_game_scores`/`cumulative_score`
are still accepted as parameters, not derived here: tracking cross-sub-game
cumulative scores needs state spanning more than one sub-game's own process
lifetime (one `Orchestrator` instance is one sub-game's own lifetime, per
PRD 6's own I1 invariant) — genuinely external data, not something to
silently invent a fake source for.

Known simplification, flagged rather than silently shipped: attaches only
`result_<game_id>.json`, not all four Table 20 files `send_report_bundle`'s
own docstring describes as the real end-of-game call's shape
(`PRD-7-reporting-shell.md`'s own Design Question 8a). The other three
(`declaration_`, `config_`, `log_`) need data this method has no clean
source for yet either (a `DeclarationBundle` needs `started_at`/`ended_at`
timestamps and `token_budget_per_series` this repo doesn't track as
instance state; the raw config file's own path isn't kept anywhere past
construction) — scoped out of TODO8 §5 rather than guessed at.
"""

from __future__ import annotations

from .domain.scoring import Outcome
from .integrity.audit import run_mutual_audit
from .integrity.step0 import current_git_commit_hash
from .observability.cost import aggregate_tokens
from .tools.gmail_sender import get_service, send_report_bundle
from .tools.report_bundle import ResultBundle, build_result, result_filename


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
        await self.send_final_reveal_to_peer(peer_url)
        self_audit = run_mutual_audit(self.log_path, self._pending_nonces)
        peer_audit = self.audit_peer()

        if is_counted:
            self.league_ledger.record_counted_game(opponent_id)

        totals = aggregate_tokens(self.log_path)
        bundle = ResultBundle(
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
        result = build_result(bundle)

        email_mode = self.private_config.email_mode
        # `send_report_bundle` never touches `service` at all under
        # "draft" — skip `get_service()` (a real token.json, unavailable
        # in this environment) entirely rather than pay a cost this call
        # path was never going to need.
        service = None if email_mode == "draft" else get_service()
        game_id = f"{self.private_config.group_id}_g{self.private_config.sub_game_number:02d}"
        return self.gatekeeper.execute(
            send_report_bundle,
            service,
            self.private_config.email_recipient,
            f"Match result — {game_id}",
            f"Outcome: {outcome.value}",
            {result_filename(game_id): result},
            email_mode=email_mode,
        )
