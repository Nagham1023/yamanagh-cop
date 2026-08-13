# TODO16 — Build Checklist for PRD 16 (Real Series-Scoped `result_<game_id>.json`)

Status: **Built & verified, including a real post-ship correction.** Read `PRD/PRD-16-series-result-report.md` in full first — it records the two root causes found, four scoping decisions (one confirmed with the user before building: `mutual_agreement` stays a local hash, not a new bilateral handshake), and a correction made after the first version shipped: the report must be sent once per *series*, not once per *sub-game* — `league_ledger.py` needed no change at all; the fix was entirely in `report_game()`'s own control flow (§6 below).

## 1. Retain the peer's own Step-0 declaration

- [x] `orchestrator.py::__init__` — `self._opponent_declaration: Step0Declaration | None = None`, next to `self._opponent_repos`.
- [x] `orchestrator_step0.py` — both call sites (`_on_step0_received`, `negotiate_step0`) keep the declaration `_verify_peer_step0` already returns, instead of discarding it via `_`.
- [x] Test: `test_orchestrator_step0.py`'s successful-negotiation test extended to assert `_opponent_declaration.group_name`/`.code_commit_hash` match what the peer actually sent, on both sides.

## 2. `SubGameEntry` + schema builders

- [x] `tools/report_bundle_result.py` (new) — `winner_and_tie`, `SubGameEntry` (`roles` fixed to cop/thief since this repo can only ever report on games it played as cop; `opponent_commit`/`opponent_score` real, `tokens[opponent]` honestly `None`; `audit.tampered = not (log_verified and peer_audit_passed)`), `build_mutual_agreement`.
- [x] `tools/report_bundle_series.py` (new, split from the above once both landed together and the file re-hit 150 lines) — `_build_final_result` (aggregates `is_counted=True` entries only), `merge_into_series_result` (`game_uid` generated once and reused; `sub_games` keyed by `sub_game_number`, idempotent re-submission; `repo_urls`/`links` real top-level fields — **caught and fixed before any test ran**: an early draft computed `repo_urls` and then discarded it while restructuring the schema, which would have silently regressed rule 49's own "four links" FATAL requirement).
- [x] 14 tests in `test_report_bundle_result.py`: winner/tie derivation, audit-tampered logic, mutual_agreement confirmed/sha256-changes-with-payload, fresh-series game_uid generation, second-call accumulation, same-sub-game-number idempotent update, warm-up exclusion from `final_result`, series tie, diversity-reward-only-on-first-meeting-win.

## 3. `report_game()` — real local persistence + read-back + merge

- [x] `orchestrator_report_entry.py` (new, split from `orchestrator_end_of_game.py` once it re-hit 150 lines) — `_opponent_repo_url` (unchanged), `_build_sub_game_entry` (raises if `_opponent_declaration is None`, same "never silently emit a fabricated value" posture as `_opponent_repo_url`).
- [x] `orchestrator_end_of_game.py::report_game` — `declaration_`/`result_` now real files at `Path(self.log_path).parent / <filename>`; `result_<game_id>.json` read back before merging (`None` on the series' own first sub-game); `num_sub_games` read from the raw shared config dict's `network_and_league.num_games`, not added to `GameConfig` (matches `PARAMETERS.md`'s own existing deferral of most league/gatekeeper fields).
- [x] `report_game`'s signature: `score: Score` replaces `sub_game_scores`/`cumulative_score` — accumulation now happens inside `report_game()` via `merge_into_series_result`, not the caller.
- [x] `tools/report_bundle.py` — `ResultBundle`/`build_result` removed (dead once `report_game()` stopped calling them); module docstring updated.
- [x] `cli_peer.py::_run_match_body` — passes `score=score_outcome(outcome, config)`; the now-unused `game_id` parameter removed from the function signature (both call sites use `_game_id` to keep the unpacked tuple shape from `build_orchestrator`).
- [x] `scripts/watch_prd8_live_match.py` — updated: sets `client._opponent_declaration` directly (its fake thief peer never runs a real Step-0 negotiation), passes `score=` instead of the old two params.
- [x] Ripple fixes: `tests/unit/test_report_bundle.py` (removed the dead `ResultBundle`/`build_result` test), `tests/unit/test_orchestrator_end_of_game.py` (full rewrite — new `_client`/`_opponent_declaration` helpers, `repo_urls`-on-disk assertions replacing the old `build_result` monkeypatch spies, two new rejection tests), `tests/unit/test_cli_peer.py` (confirmed clean, no changes needed).

## 4. Tests for real series accumulation

- [x] `test_report_game_attaches_all_four_table_20_files` extended: asserts the emailed `result_` attachment's content matches what's actually on disk (`on_disk == result_payload`), not just that the attachment exists.
- [x] `test_report_game_raises_when_opponent_declaration_is_missing` (new) — the second, distinct rejection path from the existing repo-url one (house rule: prove rejection, not just acceptance).
- [x] `test_two_sequential_real_sub_games_genuinely_accumulate_not_overwrite` (new) — two genuinely separate `Orchestrator` instances (matching PRD 10's real one-process-per-sub-game shape, not one instance calling `report_game` twice), same `game_id`/`tmp_path`: `sub_games` has both entries in order, `final_result.total_score` sums both (not just the second call's own score), `game_uid` stays identical across both real calls.

## 5. Documentation

- [x] `PRD/PRD-16-series-result-report.md` — the design doc, all four decisions with reasoning, the rule-49 near-miss caught before shipping, and the send-gating correction (§6).
- [x] `README.md` — new paragraph noting `result_`/`declaration_` are now real on-disk files with the fuller ch. 9.4 schema, pointing at PRD-16.

## 6. Correction, made after the first version shipped: send once per series, not per sub-game

- [x] User-caught real bug: ch. 9.4's own wording is that `result_<game_id>.json` is "the summary and final result for the **whole** series" — the first version sent an email after every single sub-game, re-attaching the growing result each time.
- [x] `league_ledger.py` needed **no change** — its "one counted game per `opponent_id`" enforcement was correct all along; the composition problem was entirely in `report_game()`'s own control flow.
- [x] `orchestrator_end_of_game.py::report_game` — after persisting the merged result to disk (unchanged, still happens every call), gates the rest (declaration write, attachment bundle, Gatekeeper/email dispatch) on `entry.sub_game_number == num_sub_games`; every earlier call returns `None` having only written the running result.
- [x] `scripts/watch_prd8_live_match.py` — its demo client's `sub_game_number` set to the series' own last sub-game (6), so the demo still exercises the real send path instead of only ever hitting the "not yet final" branch; print statement corrected to not misattribute the `None` to draft mode alone.
- [x] Tests: `test_report_game_does_not_send_before_the_series_final_sub_game` (new) — a non-final sub-game returns `None`, never reaches the Gatekeeper, but still persists its own entry to disk (proving accumulation itself is untouched by the gate). `_final_sub_game_client` helper added; the existing per-call tests that need the actual send path (`..._calls_each_step_in_the_documented_order`, `..._attaches_all_four_table_20_files`, `..._returns_cleanly_under_draft_mode`) switched to it.
- [x] Full regression: 46 tests across `test_orchestrator_end_of_game.py`/`test_cli_peer.py`/`test_report_bundle.py`/`test_report_bundle_result.py`/`test_orchestrator_step0.py`/`test_orchestrator.py` all pass.

## Explicitly out of scope

- [ ] A real bilateral cryptographic handshake for `mutual_agreement` — confirmed with the user, decided against; local hash + audit-derived `confirmed` instead.
- [ ] The opponent's own token-consumption reporting — no existing protocol transmits it.

## Also verify

```bash
uv run pytest tests/unit/test_report_bundle_result.py tests/unit/test_orchestrator_end_of_game.py tests/unit/test_orchestrator_step0.py tests/unit/test_orchestrator.py tests/unit/test_cli_peer.py tests/unit/test_report_bundle.py -q
uv run ruff check src/cop/tools/ src/cop/orchestrator.py src/cop/orchestrator_step0.py src/cop/orchestrator_end_of_game.py src/cop/orchestrator_report_entry.py src/cop/cli_peer.py
wc -l src/cop/tools/report_bundle*.py src/cop/orchestrator_end_of_game.py src/cop/orchestrator_step0.py src/cop/orchestrator_report_entry.py src/cop/cli_peer.py
python .claude/skills/spec-guard/scripts/check_config.py config/shared/config_dev_g01.json
git log --all --full-history -- '*credentials*' '*token.json*'
```
