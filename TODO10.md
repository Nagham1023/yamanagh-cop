# TODO10 — Build Checklist for PRD 10 (CLI, Complete Bundle, Online Readiness)

Status: **Done.** Read `PRD/PRD-10-cli-and-online-readiness.md` in full first — its Retrospective documents three real gaps found *after* this checklist's own first pass was all green: a doubled-suffix filename bug (found by literally running the CLI), a related `declaration_`/`result_` filename inconsistency and a genuine race condition in `await_passive_step0` (both found by a scoped `rule-auditor` pass), and a `ValueError` reaching the CLI uncaught. All fixed and re-verified before this status line was written — §2 and §5/§6 below reflect the corrected design, not the first draft.

## 1. `config/game.toml` / `PrivateConfig` — `initiate_step0`, `step0_wait_seconds`

- [x] Two new `[network]` fields, both `.get()`-defaulted (`False`/`300.0`) — an older config file predating this PRD keeps loading unchanged.
- [x] Test: loads real `config/game.toml`'s own defaults. Test: round-trips when present. Test: defaults safely when absent.

## 2. `orchestrator_step0_wait.py` — the passive wait

- [x] New mixin, `Step0PassiveWaitMixin`, split out of `orchestrator_step0.py` (would have crossed 150 lines otherwise).
- [x] `self._step0_received_event`/`_step0_received_loop`/`_step0_failure`/`_step0_completed` — new `Orchestrator.__init__` state, same shape as PRD 8's `_capture_response_*` trio plus one addition (`_step0_completed`, below).
- [x] `_on_step0_received` (`orchestrator_step0.py`) calls `self._signal_step0_received(...)` on both its outcomes — sets `_step0_completed = True` unconditionally, wakes a waiter only if one already exists (`_step0_received_loop` still `None` is the common, non-CLI case).
- [x] `await_passive_step0(timeout_seconds)` — checked and **corrected after `rule-auditor`'s own reproduced finding** (see "Found only by actually running this layer" below): checks `self._step0_completed` *twice* — before touching any state, and again right after the loop is set — before ever resetting `state_machine` to `NEGOTIATING`. Only proceeds to actually wait once both checks confirm nothing resolved it first.
- [x] Test: succeeds when the peer genuinely initiates (`asyncio.gather` of both sides). Rejection test: times out cleanly (bounded, not a hang) when nobody ever initiates. Rejection test: relays the *same* `Step0MismatchError` the callback detected, not a generic one. Regression test: does **not** discard a negotiation that already completed *before* `await_passive_step0` was ever called (calls `negotiate_step0` to completion first, then `await_passive_step0`, asserts near-instant return and untouched state) — both the success and failure variants.

## 3. Nonce self-sufficiency (`orchestrator_peer_audit.py`, `replay_viewer.py`)

- [x] `send_final_reveal_to_peer` logs `nonces_revealed` (string-keyed, same convention `receive_final_reveal` already uses) before attempting the send — unconditional, not gated on success.
- [x] `nonces_from_log(log_path)` (new) — scans the JSONL log for that event; raises `ValueError` with a clear reason when absent.
- [x] Test: nonces logged even when the send fails (network error) — self-audit sufficiency doesn't depend on peer reachability.
- [x] Test: `nonces_from_log` matches the live process's own `_pending_nonces` exactly. Test: round-trips through a real `ReplayViewer` verification. Rejection test: a log with no Final Reveal raises clearly.

## 4. `started_at`/`ended_at` (`orchestrator_game_loop.py`)

- [x] `play_game()` stamps `self._match_started_at` at entry, `self._match_ended_at` right before every return (both the ordinary-outcome path and the technical-loss early return).
- [x] Test: both stamped on an ordinary outcome, `started_at <= ended_at`. Test: both stamped even on a technical loss.

## 5. `report_bundle.py` loaders + `report_game()`'s complete bundle

- [x] `load_config_dict(path)` / `load_log_entries(path)` — pure functions, the raw negotiated config as-is and the JSONL trace parsed into a list.
- [x] `DeclarationBundle.started_at` widened to `str | None` — a caller that never ran `play_game()` first (several pre-existing tests) still works, honestly reporting `null`.
- [x] `report_game()` builds and attaches all four Table 20 files in one `send_report_bundle` call — **corrected after `rule-auditor`'s own finding**: `game_id` (the bare Table 20 token, `PARAMETERS.md`) is used for all four calls now — `declaration_`/`result_` take only `game_id`; `config_`/`log_` take `game_id` *and* `sub_game_number` separately, appending their own `_g{NN}`. A separate `subject_id` (the compound, human-readable form) is built just for the email subject line, which isn't part of Table 20's naming contract.
- [x] Test: all four filenames present with correct names (matching the corrected bare-`game_id` convention), each round-trips through `json.dumps`/`json.loads` cleanly, `log_` payload contains the real `nonces_revealed` event.
- [x] Full pre-existing `test_orchestrator_end_of_game.py`/`test_report_bundle.py` suites re-run — zero regressions.

## 6. The CLI (`__main__.py`, `cli_peer.py`, `cli_replay.py`)

- [x] `__main__.py` — thin `argparse` + dispatch only; real logic lives in the two sibling modules. Catches both `Step0MismatchError` and `ValueError` (a real rule-52 violation, `rule-auditor`'s own finding) for a clean `sys.exit(1)`, never a raw traceback.
- [x] `cli_peer.py::run_peer` — load configs → construct `Orchestrator` → `run_as_server` in a background thread → `negotiate_step0` or `await_passive_step0` per `initiate_step0` → `play_game` (always, both sides) → `report_game` (`sub_game_scores`/`cumulative_score` from `domain/scoring.py::score_outcome`, reused not reinvented).
- [x] `cli_replay.py::run_replay` — headless verdict + exit code by default; `--gui` additionally opens the real `ReplayViewerWindow`.
- [x] `--counted` (default off, confirmed with user), `--tunnel` (default off), `--private-config`/`--shared-config` overrides (mainly for this layer's own tests).
- [x] Test: two real, independent `run_peer()` calls (one initiator, one passive) via `asyncio.gather`, reaching a real completed and reported match — negotiated repos, `--counted` actually reaching the league ledger. Test: `--counted` omitted stays uncounted. Rejection test: the passive side times out cleanly when nobody ever initiates.
- [x] Test: `run_replay` — verified-ok exit 0, tampered exit 1, missing-Final-Reveal exit 1 with a clear stderr message.
- [x] `uv run python -m cop peer --help` / `replay --help` checked live — matches the documented interface exactly.

## 7. `scripts/setup_gmail_oauth.py`

- [x] One-time `InstalledAppFlow` consent script, reusing `gmail_sender.SCOPES` directly (never redefined — rule 30's send-only scope stays single-source).
- [x] Checked live: a clear, specific error (not a stack trace) when `credentials.json` is absent — this development environment has none, confirmed the failure mode is legible rather than exercising the real OAuth flow (impossible here, needs a browser + real Google credentials).

## Found only by actually running this layer (or by `rule-auditor`'s own pass)

- **A doubled-suffix filename bug**, found only by running `uv run python -m cop peer` as two real subprocesses and reading the actual files under `logs/` — not by any unit test. `config_filename`/`log_filename` (`report_bundle.py`) each append their own `_g{NN}` from a separate `sub_game_number` argument; the first draft of both `report_game()` and `run_peer()`'s log-path default passed them the already-suffixed `game_id` instead of the bare `group_id`, producing `config_dev-team_g01_g01.json`. The one test checking attachment filenames had the same bug baked into its own expected values, so the full suite stayed green while the bug shipped.
- **`declaration_`/`result_filename` were *also* wrong, the opposite way — found by `rule-auditor`**, checking against `PARAMETERS.md`'s actual Table 20 text and `report_bundle.py`'s own pre-existing test contract. Both should take only the bare `game_id`, no sub-game suffix at all (one evolving pair of files per series) — the filename-doubling fix above only closed half the inconsistency.
- **A real, empirically-reproduced race in `await_passive_step0`** — `rule-auditor`'s most serious finding, not found by any test in this layer's own first draft: reusing PRD 8's cross-thread `Event`/`call_soon_threadsafe` pattern wasn't automatically sufficient, because `orchestrator_capture.py`'s own safety argument depends on the loop being set *before the send that causally triggers the response* — `await_passive_step0` has no such trigger, so a negotiation the peer completes during the CLI's own 0.5s startup grace window (a completely ordinary timing in a real two-machine match) could be silently discarded and replaced with a spurious 300-second timeout. Fixed with `self._step0_completed`, checked twice; two new regression tests reproduce the exact race by calling `negotiate_step0` to completion *before* `await_passive_step0`.
- **A `ValueError` from a genuine rule-52 violation reached `main()` uncaught** — `rule-auditor`'s smaller finding; rule 52 was never actually bypassable, this was a CLI robustness gap only. Fixed with one more `except` clause.
- **The replay-log nonce gap** (§3) wasn't in either of the two originally-named polish items — found while mapping what the documented `replay --log <path>` command would actually need to do, before any CLI code was written. Confirmed real (not hypothetical) by reading `orchestrator_peer_audit.py`/`integrity/audit.py`/`observability/trace.py` directly: `send_final_reveal_to_peer` logged only `step_count`, never the nonces themselves.
- **`run_peer()` needed overridable `log_path`/`league_ledger_path`** — not anticipated at design time, found while writing this layer's own two-real-process CLI test: `Orchestrator.__init__`'s own defaults are shared, single files (`logs/trace.jsonl`, `logs/league_ledger.json`); two concurrent `run_peer()` calls in one test process would otherwise collide on both.
- **`token_budget_per_series` was already on `GameConfig`**, not missing as `report_bundle.py`'s own pre-PRD-10 docstring claimed — same kind of stale-claim drift PRD 9 found and fixed for `verify_config_identity`. Corrected in the same pass rather than re-flagged for later.

## Cleanup and final verification

- [x] Every new/touched module re-checked against the 150-line house cap — `orchestrator_step0.py` needed the `orchestrator_step0_wait.py` split; `orchestrator.py` needed further comment trims to stay at 150 after the new constructor state (including `_step0_completed`) landed; `orchestrator_end_of_game.py` needed a docstring trim after the filename-convention fix.
- [x] Full `uv run pytest`, run in batches — 483 unit + 8 integration tests green (491 total), 99% combined coverage; zero regressions across every pre-existing suite touched.
- [x] Literal `uv run python -m cop peer` run as two real subprocesses (not just the Python-level `run_peer()` tests), **twice** — once before the fixes (caught the filename bug), once after (confirmed `logs/log_smoke-a_g01.json`, correct, and `uv run python -m cop replay --log <path>` printing `Verified OK` against it).
- [x] `rule-auditor` run scoped to rules 6/7/18/20/34/49 — found the two gaps above (declaration_/result_ filenames, the `await_passive_step0` race), both fixed and re-verified before this line was written.
- [x] `uv run ruff check .` — clean.
- [x] `check_config.py config/shared/config_dev_g01.json` — still 33/33.
- [x] `git log --all --full-history -- '*credentials*' '*token.json*' '*.env'` — still empty.
- [x] `instructions.md` written — full submission-readiness scope (confirmed with user), not just "run one game."
- [x] `TODO.md`'s own master checklist — PRD 10 section added.
- [x] `PRD/PRD-10-cli-and-online-readiness.md` written and built; commit.
