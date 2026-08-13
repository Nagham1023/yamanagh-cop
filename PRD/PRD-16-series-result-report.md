# PRD 16 — Real series-scoped `result_<game_id>.json`

## The gap this closes

A spec-compliance pass checked ch. 9.4's final result report schema and the "four game JSONs + two auth JSONs" file inventory against what's actually built.

**The auth-file half was already fully correct.** `.gitignore` genuinely covers `credentials.json`/`token.json`/`client_secret*.json`/`*credentials*.json`/`*token*.json`/`secrets.json`, and `git log --all --full-history` confirmed neither has ever been committed (rule 39, clean). Nothing to build here.

**The four game-JSON half had a real, previously-undocumented gap.** `declaration_`/`config_`/`log_` already matched the book exactly (one static per-series declaration, one config/log pair per sub-game). `result_<game_id>.json` (`src/cop/tools/report_bundle.py::build_result`, now removed) was a flat, single-sub-game-scoped dict — `sub_game_scores`, `cumulative_score`, `code_commit_hash`, `total_tokens`, four flat repo-link fields, two audit booleans — with no `schema_version`/`game_uid`/`timezone`/`links`/`groups`/`sub_games` array/`final_result` object/`mutual_agreement` block.

Two root causes, both confirmed by reading the actual call path before designing a fix:

1. **No real series accumulation.** `report_bundle.py`'s own old docstring already claimed `ResultBundle.sub_game_scores` "accumulates per-sub-game data" — but `cli_peer.py` passed a fresh single-entry `{game_id: score.cop}` dict on every single CLI run, and nothing ever read a previous result back to merge into it. Root cause: `gmail_sender.py::build_message` only ever built an in-memory MIME attachment — no Table 20 file was ever actually written to local disk, so there was nothing to read back between the six separate sub-game process lifetimes (PRD 10's "one `Orchestrator` per sub-game" design).
2. **The peer's own Step-0 declaration was verified then discarded.** `orchestrator_step0.py::_verify_peer_step0` returned `(declaration, validated_repos)` at both call sites (`_on_step0_received`, `negotiate_step0`) — both discarded the declaration via `_`, keeping only `validated_repos`. So the opponent's own `group_name`/`code_commit_hash` — needed for `groups` and per-team `github_commit` — weren't retained anywhere.

## Decisions

**`mutual_agreement` — a locally-computed hash, not a new bilateral handshake (confirmed with the user before building).** `sha256` over the canonical result payload (`integrity/canonical_json.py`, the same encoding every other `integrity/` hash uses), `confirmed = self_audit_passed and peer_audit_passed`. Real and independently verifiable — a lecturer can recompute the exact hash over the received JSON — but honest about what it actually checks: this side's own two audits both passing, not a new round-trip where the peer independently confirms agreement on this exact payload. That would be a materially larger protocol addition (a new MCP tool, a new commit-reveal-shaped round trip specifically over the final summary) — decided against for this PRD.

**`repo_urls` — a real, top-level field, not dropped.** Rule 49 (**[FATAL]**): "four links in both teams' JSON." An early draft of `merge_into_series_result` computed the opponent's repo URLs and then discarded them while restructuring the schema around the richer `sub_games`/`groups` shape — caught before any test ran, by re-reading rule 49's actual binding text rather than assuming the new schema's own `links` concept (file cross-references) covered it. Fixed: `repo_urls` (`{this_cop, this_thief, opponent_cop, opponent_thief}`) is a real top-level field, computed fresh every call since it doesn't change sub-game to sub-game. `links` is a second, distinct field — `{"declaration": declaration_filename(game_id)}` — since `config`/`log` filenames already live inside each `sub_games` entry's own `log_files`.

**`roles` is fixed, not derived.** `{this_group: "cop", opponent_group: "thief"}` on every entry — this repo can only ever report on games it played as cop (rule 1/2). Not a gap; a repo that could report the reverse would itself be a rule 1/2 violation.

**Opponent-side `tokens` stays honestly `None`.** No existing protocol transmits the opponent's own token consumption to this side. Reporting a fabricated or zero value would be worse than omitting it.

**`diversity_reward_applied` is self-reported, not lecturer-authoritative** — matching `league_ledger.py`'s own already-established philosophy ("make the truthful path easy; real enforcement is the lecturer's cross-reference between both sides' independent reports"). Computed as `first_meeting_between_groups and this_group_won_the_series_so_far` (Table 18 row 4's own condition), not overridden or second-guessed here.

**`final_result` aggregates only `is_counted=True` entries** — matching `league_ledger.py`'s own "warm-ups are never recorded" scope exactly. A warm-up still appears in the raw `sub_games` array (visible, not hidden) but never moves `total_score`/`sub_games_won`/`ties`/`winner_group`.

## A real correction, made after the first version shipped

The first version of `report_game()` sent an email after *every* sub-game, each time re-attaching the full, growing `result_<game_id>.json`. Wrong: ch. 9.4's own wording is that the result report is "the summary and final result for the **whole** series" — one report, sent once, not six. The corrected design keeps the per-sub-game write-and-merge (still necessary — each sub-game really is a separate `Orchestrator` process, PRD 10, and something has to persist the running tally between them) but gates the actual Gatekeeper/email dispatch on `entry.sub_game_number == num_sub_games`: every earlier call returns `None` having only written the merged result to disk; the series' own last sub-game builds the attachment bundle and sends. `league_ledger.py`'s "one counted game per `opponent_id`" enforcement was correct all along and needed no change — the composition problem was entirely in `report_game()`'s own control flow (when it sent), not in what `league_ledger.py` enforces. The "explicitly out of scope" item from the first version of this doc (reconciling the two) is resolved by this fix, not left open.

## What got built

- `src/cop/orchestrator.py`, `src/cop/orchestrator_step0.py` — `self._opponent_declaration` retained at both Step-0 call sites.
- `src/cop/tools/report_bundle_result.py` (new) — `SubGameEntry`, `winner_and_tie`, `build_mutual_agreement`.
- `src/cop/tools/report_bundle_series.py` (new) — `merge_into_series_result`, `_build_final_result` (split from `report_bundle_result.py` once both landed together and the file re-hit the 150-line cap).
- `src/cop/orchestrator_report_entry.py` (new) — `_opponent_repo_url`, `_build_sub_game_entry` (split from `orchestrator_end_of_game.py`, same reason).
- `src/cop/orchestrator_end_of_game.py` — `report_game()` now writes `declaration_<game_id>.json`/`result_<game_id>.json` to real local disk (`Path(self.log_path).parent`, the same field tests already override to `tmp_path`), reads the previous `result_<game_id>.json` back before merging, and attaches the merged (not per-sub-game) payload — but only actually reaches the Gatekeeper/email send on the series' own last sub-game (`entry.sub_game_number == num_sub_games`); every earlier call returns `None` having only persisted the merge. `score: Score` replaces the old `sub_game_scores`/`cumulative_score` params — accumulation now happens inside `report_game()` itself, not the caller.
- `src/cop/tools/report_bundle.py` — `ResultBundle`/`build_result` removed (dead code once `report_game()` stopped calling them); declaration/config/log builders untouched.
- `src/cop/cli_peer.py` — `_run_match_body` passes `score=score_outcome(outcome, config)` instead of the old two params; the now-unused `game_id` parameter removed.
- `scripts/watch_prd8_live_match.py`, `tests/unit/test_orchestrator_end_of_game.py`, `tests/unit/test_report_bundle.py`, `tests/unit/test_cli_peer.py` — updated for the new `report_game()` signature; the demo script and the "no negotiation happened" tests set `_opponent_declaration` directly, the same shortcut already used for `opponent_*_repo_url` overrides.

## Also verify (acceptance criteria)

```bash
uv run pytest tests/unit/test_report_bundle_result.py tests/unit/test_orchestrator_end_of_game.py tests/unit/test_orchestrator_step0.py tests/unit/test_orchestrator.py tests/unit/test_cli_peer.py tests/unit/test_report_bundle.py -q
uv run ruff check src/cop/tools/ src/cop/orchestrator.py src/cop/orchestrator_step0.py src/cop/orchestrator_end_of_game.py src/cop/orchestrator_report_entry.py src/cop/cli_peer.py
wc -l src/cop/tools/report_bundle*.py src/cop/orchestrator_end_of_game.py src/cop/orchestrator_step0.py src/cop/orchestrator_report_entry.py src/cop/cli_peer.py   # all ≤150
python .claude/skills/spec-guard/scripts/check_config.py config/shared/config_dev_g01.json
git log --all --full-history -- '*credentials*' '*token.json*'   # still nothing
```

## Explicitly out of scope

- A real bilateral cryptographic handshake for `mutual_agreement` (decided against — see "Decisions" above).
- Extending the opponent's own token-consumption reporting — no existing protocol transmits it; would need a new wire field on an existing message, not something this PRD's own scope covers.
