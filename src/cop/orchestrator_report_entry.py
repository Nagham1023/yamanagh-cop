"""PRD 16: builds this sub-game's own `SubGameEntry` — split out of
`orchestrator_end_of_game.py`, which re-hit the 150-line cap once the real
series-accumulation logic landed alongside `report_game()` itself.
"""

from __future__ import annotations

from .domain.scoring import Outcome, Score
from .integrity.step0 import current_git_commit_hash
from .observability.cost import aggregate_tokens
from .tools.report_bundle import config_filename, log_filename
from .tools.report_bundle_result import SubGameEntry


class ReportEntryMixin:
    def _opponent_repo_url(self, role: str) -> str:
        if self._opponent_repos is None:
            raise ValueError(
                f"opponent_{role}_repo_url was not supplied and no Step-0 "
                f"negotiation has completed (self._opponent_repos is None) "
                f"— call negotiate_step0() first, or pass it explicitly."
            )
        return self._opponent_repos[role]

    def _build_sub_game_entry(
        self, outcome: Outcome, score: Score, self_audit_passed: bool, peer_audit_passed: bool, is_counted: bool
    ) -> SubGameEntry:
        """Rule 49: the opponent's own group/commit come from the Step-0
        declaration Step-0 already verified and PRD 16 now retains — raises
        rather than silently emitting a fabricated/empty value, same
        posture as `_opponent_repo_url`."""
        if self._opponent_declaration is None:
            raise ValueError(
                "self._opponent_declaration is None — call negotiate_step0()/"
                "await_passive_step0() first; the opponent's own group_name/"
                "code_commit_hash have no other honest source."
            )
        game_id = self.private_config.group_id
        sub_game_number = self.private_config.sub_game_number
        return SubGameEntry(
            sub_game_number=sub_game_number,
            this_group=self.private_config.group_name,
            opponent_group=self._opponent_declaration.group_name,
            started_at=self._match_started_at,
            ended_at=self._match_ended_at,
            result=outcome.value,
            this_score=score.cop,
            opponent_score=score.thief,
            this_commit=current_git_commit_hash(),
            opponent_commit=self._opponent_declaration.code_commit_hash,
            this_tokens=aggregate_tokens(self.log_path).total_tokens,
            config_file=config_filename(game_id, sub_game_number),
            log_file=log_filename(game_id, sub_game_number),
            log_verified=self_audit_passed,
            peer_audit_passed=peer_audit_passed,
            is_counted=is_counted,
        )
