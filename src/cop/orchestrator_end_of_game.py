"""PRD 8's automatic end-of-game sequence (rules 32, 36), extended by
PRD 16 to build the real, series-scoped `result_<game_id>.json` (ch. 9.4).
The rest of the sequence — mutual audit, series-result merge, declaration
write, Gatekeeper/Gmail dispatch — lives in `orchestrator_report_dispatch.py`'s
`ReportDispatchMixin._finish_report_game`, split out so this file could wrap
that whole call in one failure-logging `try/except` (a real gap otherwise:
that tail used to have zero exception handling at all — a `ValueError` from a
missing Step-0 declaration, a `KeyError` from the shared config, a file-write
error, or a Gatekeeper/Gmail rejection all propagated completely unlogged out
of the entire match pipeline, found while auditing the pipeline's own
exception coverage) without pushing this file past the 150-line house cap.

`opponent_cop_repo_url`/`opponent_thief_repo_url` default to
`self._opponent_repos` (PRD 9); `self._opponent_declaration` (PRD 16)
supplies the opponent's own `group_name`/`code_commit_hash`.
"""

from __future__ import annotations

from .domain.scoring import Outcome, Score


class EndOfGameMixin:
    async def report_game(
        self,
        peer_url: str,
        outcome: Outcome,
        is_counted: bool,
        opponent_id: str,
        score: Score,
        opponent_cop_repo_url: str | None = None,
        opponent_thief_repo_url: str | None = None,
    ) -> dict | None:
        """Design Question 4: separate from `play_game()` itself. `score`
        replaces PRD 8's `sub_game_scores`/`cumulative_score` params —
        accumulation happens inside via `merge_into_series_result`."""
        opponent_cop_repo_url = opponent_cop_repo_url or self._opponent_repo_url("cop")
        opponent_thief_repo_url = opponent_thief_repo_url or self._opponent_repo_url("thief")
        try:
            await self.send_final_reveal_to_peer(peer_url)
        except Exception as exc:
            self.trace.log(
                "final_reveal_send_failed", error=str(exc), exception_type=type(exc).__name__
            )

        # Real race, found live: this side's own outcome can be known
        # before the peer's independently-timed Final Reveal has actually
        # landed — orchestrator_peer_audit.py's own docstring has the story.
        try:
            return await self._finish_report_game(
                outcome,
                is_counted,
                opponent_id,
                score,
                opponent_cop_repo_url,
                opponent_thief_repo_url,
            )
        except Exception as exc:
            # Everything downstream (mutual audit, series-result merge/write,
            # declaration, Gatekeeper/Gmail) used to fail completely silently
            # — this is the one thing standing between a real reporting bug
            # and a raw, unattributed traceback with nothing in the trace log
            # explaining what actually went wrong. Re-raised, not swallowed:
            # the caller (run_match_body) still needs to know this failed.
            self.trace.log(
                "report_game_failed", reason=str(exc), exception_type=type(exc).__name__
            )
            raise
