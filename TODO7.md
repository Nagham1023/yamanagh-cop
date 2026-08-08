# TODO7 — Build Checklist for PRD 7 (Reporting and Visualization Shell)

Not started. Read `PRD-7-reporting-shell.md`'s "Design questions answered here" section in full before writing any code in this checklist — several sections below depend directly on design calls made there (especially DQ2's exact local-truth boundary, DQ4's "reuse PRD 6's real machinery, not ch. 7.5's sketch," and DQ5/DQ9's already-resolved Gatekeeper numeric precedence).

## 0. Setup

- [x] Re-read `PLAN.md`'s "Gatekeeper numeric precedence" note (line ~127) and its module-tree table (line ~90-105) — `policy/gatekeeper.py`'s exact interface shape (`execute()`/`get_queue_status()`) and its config source (`rate_limiter_gatekeeper`, not a new file) are already decided there; don't re-derive them.
- [x] Confirm `.gitignore` still covers `credentials.json`/`token.json`/`.env` (it does, added pre-emptively) — know this before the first real OAuth consent flow creates either file locally.
- [x] Re-read `memory/belief.py::BeliefMap`'s public interface (`probability()`, `most_likely_cell()`, `_probabilities`) and `planner/state_machine.py::PeerStateMachine` — both get read directly by `live_gui.py`, not reimplemented.
- [x] Re-read `integrity/commit_reveal.py`/`integrity/audit.py`/`integrity/step0.py::Step0Declaration` — the Replay Viewer and `report_bundle.py` build on these exactly, don't reopen or duplicate them.
- [x] `uv add google-auth google-auth-oauthlib google-api-python-client` — the one genuinely new dependency this layer needs (PRD 7's own "New dependency" section).

## 1. `policy/token_bucket.py`

- [x] `TokenBucket` class: `__init__(self, capacity: float, refill_rate: float)`, `_refill()`, `allow(cost: float = 1.0) -> bool` — ch. 9.3.2's own worked code (p.77), shape unchanged; `capacity`/`refill_rate` are constructor params, not hardcoded, sourced by the caller from config (rule I6: nothing hardcodes a quantitative value).
- [x] Test: a fresh bucket at full capacity allows `capacity` calls in immediate succession, then blocks the next one.
- [x] Test: after blocking, waiting long enough for `refill_rate * elapsed >= 1` allows exactly one more call — prove the refill math, not just the block.
- [x] Test: `_refill()` clamps at `capacity` — a very long wait doesn't let tokens accumulate past the ceiling (this is `min(C, ...)` in the book's own formula; write the rejection test that would catch it silently missing).
- [x] Rejection test: `allow(cost=0)` or a negative cost doesn't let an unlimited number of calls through for free — decide the exact guard (reject non-positive cost outright) and test it.

## 2. `policy/quota_manager.py`

- [x] `QuotaManager` class: tracks a daily request count (reset at UTC midnight or per-process start — decide which, document why), `allow() -> bool`, exposes the current count for `get_queue_status()`.
- [x] Test: allows requests up to a configured daily ceiling, blocks the one past it.
- [x] Test: the count resets appropriately at the boundary condition chosen above — write the test that actually exercises the reset, not just the blocking behavior.
- [x] Rejection test: a caller cannot bypass the count by constructing a second `QuotaManager` instance mid-run if the design intends a single shared counter — decide whether this needs a persisted/shared counter or an in-process one is acceptable given this repo's own single-process-per-role Orchestrator lifetime (rule 1/2 already guarantees no cross-role sharing; this is a same-role, same-process concern only).

## 3. `policy/dos_detector.py`

- [x] `DosDetector` class implementing PRD 7's own Design Question 7 choice: N consecutive Gatekeeper-approved sends within a short rolling window with no successful response in between trips `LOCKED`. Constants (N, window seconds) live in this module, not hardcoded inline, and are documented as this repo's own choice (not book-required — same "book gives the concept, not the number" label already used for the belief-map reliability coefficient).
- [x] `record_attempt()`/`record_success()`/`is_locked() -> bool` (or similar — decide the exact API surface before writing tests).
- [x] Test: N consecutive attempts with no intervening success trips `LOCKED`.
- [x] Test: a success in between resets the counter — the detector doesn't lock on a healthy, if bursty, sending pattern.
- [x] Rejection test: once `LOCKED`, further `record_attempt()` calls don't un-lock it on their own — only an explicit reset (a human action, matching the book's own "manual reset" framing for a circuit breaker) clears it.

## 4. `policy/gatekeeper.py` — `ApiGatekeeper`

- [x] `ApiGatekeeper.__init__(self, config: ...)` — reads `rate_limiter_gatekeeper` fields from the negotiated `GameConfig` (extend `GameConfig`/`from_dict` to read this block — currently unread, confirmed via `PARAMETERS.md`'s own note), constructs its own `TokenBucket`/`QuotaManager`/`DosDetector` internally.
- [x] `execute(self, api_call, *args, **kwargs)` — the guide's own required signature (`software_submission_guidelines-V3.pdf` §5.1): runs Quota Manager → Token Bucket → DOS Detector in that order (ch. 9.3.1, Fig. 13's own left-to-right flow), fail-fast at the first gate that rejects (raise or return a typed rejection — decide which, document why), only then calls `api_call(*args, **kwargs)`; logs every call (approved or rejected) for `get_queue_status()`.
- [x] `get_queue_status(self) -> QueueStatus` (or a plain dict/dataclass — decide) — queue depth, rejection counts by gate, matching the guide's own interface.
- [x] Test: a call that clears all three gates actually reaches the wrapped `api_call`.
- [x] Test: a call rejected by the Quota Manager never reaches the Token Bucket or the wrapped call — prove fail-fast ordering, not just eventual rejection.
- [x] Test: a call rejected by the Token Bucket never reaches the DOS Detector or the wrapped call.
- [x] Test: `get_queue_status()` reflects a rejection that just happened.
- [x] Sanity-check by sabotage: temporarily make `execute()` skip straight to `api_call` without running any gate, confirm the "past capacity" test built above actually fails, then revert.

## 5. `policy/league_ledger.py`

- [x] `LeagueLedger` class (or module-level functions over a small persisted/in-memory structure — decide): `record_counted_game(opponent_id: str) -> None`, `is_already_counted(opponent_id: str) -> bool`, `counted_game_count() -> int`, `declare_at_game_start() -> int` (rule 37 — the truthful count to put in the declaration file).
- [x] Test: recording a counted game against a new opponent succeeds and increments the count.
- [x] Rejection test: recording a *second* counted game against an already-counted opponent raises/refuses (rule 52 **[FATAL]** — one counted game per opponent) — distinguish this from a warm-up, which is untracked here entirely (ch. 9.2.1: warm-ups are permitted, not counted, tracking them isn't this module's job).
- [x] Test: `declare_at_game_start()` returns the true count, not a stale or hardcoded one, across multiple recorded games.

## 6. `integrity/peer_trace.py` — the genuinely bilateral half of the mutual audit (rule 36, Design Question 11)

Closes PRD 6's own "Known gap" for real — re-read ch. 5.4 directly before starting: the mutual audit is each side reconstructing and verifying the **peer's** own committed-and-revealed data, not a self-check. `test_audit.py`'s existing adversarial test only proves the self-audit half; this section's own adversarial test (below) must prove the *peer*-audit half separately — they are not the same claim.

- [x] Extend `orchestrator_turn.py::_on_reveal_received(move, hint_text)` to persist `(move, hint_text, step)` — currently `del move` discards it outright (`# unverified claim... not consumed here`). Persisting is not the same as trusting it: still don't fold `move` into belief state here (DQ2 from PRD 6 stands — it's an unverified claim until Final Reveal), only record it for later audit use.
- [x] Wire `on_commit` (`build_server`'s existing, currently-`None` callback) to persist the peer's `(h_commit, step)` — mirrors this side's own `"committing"` trace entry, but for the peer's data, keyed the same way.
- [x] Wire `on_final_reveal` (also currently `None`) to persist the peer's disclosed `(nonce, step)` pairs once they arrive at game end.
- [x] `PeerTrace` structure (dataclass or similar) holding the three above, keyed by step — decide whether this lives in-memory on `Orchestrator` (same lifetime as `_pending_nonces`) or gets its own persisted log; recommend in-memory first, matching `_pending_nonces`'s own precedent, unless a real need for persistence across restarts appears.
- [x] `run_peer_audit(peer_trace: PeerTrace, role: str = "thief") -> AuditResult` — reconstructs each step's `CommitEnvelope` from the peer's own `(h_commit, move, hint_text, nonce)` and recomputes/compares via the same `integrity/commit_reveal.py::commit()`/`verify()` this repo's own `run_mutual_audit` already uses (reuse, don't reimplement — same discipline as PRD 6's own DQ4 precedent for the Replay Viewer).
- [x] Test: a genuine two-`Orchestrator` exchange (same fixture pattern `test_audit.py` already uses) — after a full commit/reveal/final-reveal cycle, `run_peer_audit` on the receiving side's own `PeerTrace` passes.
- [x] **The adversarial test that actually proves this is bilateral, not a copy of the self-audit test**: tamper a field the *peer* revealed (not a field this side committed) between commit and final-reveal, confirm `run_peer_audit` — run on the *other* side — catches it. This is the single most important test in this section: a test that only ever tampers this side's own data would silently pass even if `run_peer_audit` were accidentally just calling `run_mutual_audit` under a new name.
- [ ] **Gap, acknowledged at closing, not built this pass.** Wire both `run_mutual_audit` (self) and `run_peer_audit` (bilateral) into an automatic end-of-game sequence — not gated behind a human opening the Replay Viewer (ch. 5.4 places this "at game's end," every game). This sequence is also where `tools/report_bundle.py` (below) gets the audit outcome to fold into the result file. `rule-auditor`'s closing-pass review confirmed no such sequence exists anywhere in `src/`; see `PRD-7-reporting-shell.md`'s Retrospective — deliberately left for a dedicated future PRD/TODO rather than added without one.

## 7. `tools/gmail_sender.py`

- [x] `get_service()` — `Credentials.from_authorized_user_file("token.json", SCOPES)`, `build("gmail", "v1", credentials=creds)` (ch. 9.3, p.124's own shape). `SCOPES = ["https://www.googleapis.com/auth/gmail.send"]` — a **module-level constant**, checked by its own literal-equality rejection test (Design Question, "Also verify").
- [x] First-run consent flow: `InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)`, producing `token.json` — document this as a one-time, human-present step (Appendix A's own "opens a browser window, asks you to confirm" description), not something a test can exercise without real credentials; the test suite mocks/fakes `get_service()`'s return value instead.
- [x] `send_report(service, to_addr: str, subject: str, body: str, json_bundle: dict, attachment_filename: str) -> dict` — builds a `MIMEMultipart`, a short human-readable `body` as the text part, `json_bundle` attached as `application/json` under `attachment_filename` (Design Question 10 — never `MIMEText`-only). Base64-encodes and calls `service.users().messages().send(...)`.
- [x] `send_report_bundle(service, to_addr, declaration, config, log, result) -> dict` (or similar) — the real end-of-game call: attaches **all four** Table 20 files (declaration, config, log, result) to **one** message, not four separate sends and not a separate declaration-time send at game start (PRD 7's own Design Question 8 addendum, ch. 9.3.3).
- [x] `PrivateConfig.email_mode` branch, here and only here (`report_bundle.py`/end-of-game orchestration don't need to know about it): `"draft"` builds the bundle and the `MIMEMultipart` message but stops short of calling `service.users().messages().send(...)`; `"send"` performs the real send.
- [x] Every call to `send_report`/`send_report_bundle` goes through `ApiGatekeeper.execute()` at the call site (`orchestrator`-level wiring, not inside `gmail_sender.py` itself — keep `tools/` a thin transport layer, same rule 3/I2 discipline every prior PRD's tools module followed).
- [x] Test: `send_report`'s constructed message object has exactly one `application/json` attachment part and a separate, short text part — assert the MIME structure directly, not just that `send_report` "worked."
- [x] Test: `send_report_bundle`'s constructed message has **four** attachment parts, one per Table 20 file, in a single message — not four separate `send_report` calls.
- [x] Rejection test: `SCOPES` is not `["https://www.googleapis.com/auth/gmail.send"]` exactly — fails a literal-equality guard (catches an accidental broadening to `gmail.modify`/`mail.google.com` before it ships).
- [x] Test (mocked `service`): calling `send_report` past a 429-simulating mock response backs off per `rate_limiter_gatekeeper.retry_backoff_sec`/`max_retries` rather than retrying immediately — rule 28's own "the iron rule: respect a 429, never retry blindly."
- [x] Test: `email_mode="draft"` builds the message but the mocked `service.users().messages().send` is never called; `email_mode="send"` calls it exactly once.

## 8. `tools/report_bundle.py`

- [x] `DeclarationBundle` dataclass (or similar): embeds `Step0Declaration` (reused, PRD 6) plus `group_name`, `members: tuple[str, ...]`, `cop_repo_url`/`thief_repo_url` for this team only (own two, from `PrivateConfig.repos`), `token_budget_per_series`, `started_at`/`ended_at` timestamps. The opponent's own two links are **not** required here by the book (Design Question 8 addendum) — add them only if this repo wants the redundancy, labeled as such, not as a book requirement for this file.
- [x] `build_declaration(...) -> dict` — canonical-JSON-serializable, written to `declaration_<game_id>.json` (Table 20's exact naming, `todoFullFix.md` §G precedent).
- [x] `ResultBundle` dataclass: per-sub-game scores, cumulative series result, `code_commit_hash` (reused from `Step0Declaration`, not re-derived), `total_tokens` (from `observability/cost.py`), **all four** repo links (this team's cop+thief, the opponent's cop+thief — rule 49, textually tied to this file specifically, ch. 9.4), and the audit outcome from `integrity/audit.py::run_mutual_audit` + `integrity/peer_trace.py::run_peer_audit` (§6).
- [x] `build_result(...) -> dict` — written to `result_<game_id>.json`.
- [x] Test: `build_declaration`/`build_result` round-trip through `json.dumps`/`json.loads` cleanly (no non-serializable fields snuck in — same float/type discipline `commit_payload.py` already established).
- [x] Test: both files' names match Table 20 exactly for a given `game_id` — a literal string-format test, cheap and catches a typo before it costs a graded point.
- [x] Test: the result file contains all four repo links (this team's cop+thief, the opponent's cop+thief) — rule 49's own acceptance criterion, checked directly.
- [x] Test: a real game's `Orchestrator` (constructed by whatever end-of-game orchestration script drives this) writes its trace log to `logs/log_<game_id>_g<NN>.json`, not the bare `logs/trace.jsonl` default — checked directly against the actual file on disk, not assumed (`PLAN.md`'s own prior claim that this already matched was wrong, corrected during PRD 7's own critique pass).

## 9. `observability/cost.py`

- [x] `aggregate_tokens(trace_log_path) -> TokenTotals` (or similar) — reads whatever per-turn token count field exists in the trace log (currently always `0` under `template`/`ollama`; add the field to the trace log now even though it's always `0` today, so `claude_api`/`claude_cli` — if built later, per the optional section below — don't need a trace-log schema change to start reporting real numbers).
- [x] Test: an all-zero log (the only real case today) rolls up to `0`, honestly — not a crash, not a placeholder non-zero number.
- [x] Test: a synthetic log with non-zero per-turn token fields (simulating a future `claude_api` run) rolls up correctly — proves the aggregation math works even though no live provider produces this data yet.

## 10. `observability/live_gui.py`

- [x] A Tkinter window (Design Question 1): a grid rendering `BeliefMap._probabilities` as a heatmap (deeper red = higher probability, ch. 7.3.1), plus a turn-state banner reading `Orchestrator.state_machine.state` directly (Design Question 3 — no parallel GUI-only state).
- [x] The render function's own parameter list is the actual rule 8/9 enforcement point (Design Question 2) — it must be possible to call it with exactly `(own_pos: Position, belief_probabilities: dict[Position, float], turn_state: str)` and nothing else; no parameter admits a true opponent `Position` or a full `GameState`.
- [x] Test (introspection-based, not a screenshot): assert the render function's signature/call site never receives anything shaped like a true opponent position or an objective `Board`/`GameState` object — `PRD-7-reporting-shell.md`'s own "Also verify" methodology.
- [x] Test: feeding a real `BeliefMap` in produces a heatmap grid where the highest-probability cell is visually distinguishable (e.g. the rendered color/intensity value for that cell is strictly greater than a uniform-distribution baseline) — proves the mapping is real, not a static placeholder image.
- [x] `scripts/watch_prd7_live_gui.py` — a live demo script, same discipline as every prior PRD: two real `Orchestrator`s exchanging turns, the GUI window updating on each turn, run and watched, not just asserted in a test (this project's own "a layer is done when the behaviour was watched by a human" rule — genuinely applicable here more than anywhere else, since this *is* the visual layer).

## 11. `observability/replay_viewer.py`

- [x] A Tkinter window (same toolkit as `live_gui.py`, Design Question 1): step-forward/step-backward controls over a loaded `log_<game_id>_g<NN>.json`, a `Verified OK`/`TAMPERED` banner.
- [x] Wraps `integrity/audit.py::run_mutual_audit` (Design Question 4 — not a reimplemented, narrower verifier) — on load, runs the full audit once; per-step navigation shows that step's own individual verification status (from the same audit result, not a second recomputation).
- [x] Test: loading a genuine, untampered log produced by a real `commit_and_reveal_to_peer` exchange (same fixture pattern `test_audit.py` already uses) shows `Verified OK`.
- [x] Rejection test: loading a log with one tampered `committing` entry (same tampering technique `test_audit.py`'s own adversarial test already uses) shows `TAMPERED` and the viewer refuses to report the match as verified, even if the human clicks through every step.
- [x] `scripts/watch_prd7_replay.py` — live demo: record one real committed-and-revealed exchange, open it in the Replay Viewer, show `Verified OK` live; then tamper the log and show `TAMPERED` live — the "second, adversarial milestone" `PRD-7-reporting-shell.md`'s own Milestone section requires, demonstrated, not just tested.

## 12. Research-and-analysis deliverables

- [x] A results-analysis notebook (`notebooks/` — decide the exact location; `docs/` is also acceptable per `PLAN.md`'s own wording) reading recorded game logs, rendering: a belief-map heatmap over time, a scent-decay curve (reusing `memory/scent.py`'s own formula), a win/loss/technical-loss breakdown across the counted games played so far.
- [x] One parameter-sensitivity pass: hold everything else fixed, vary the belief-weighting between scent and hint (`memory/belief.py::_HINT_RELIABILITY`, PRD 4's own "intellectual core of the project" framing) across a handful of warm-up games, plot the effect on capture rate.
- [x] A token-cost breakdown table (model, input/output tokens, estimated cost) sourced from `observability/cost.py`'s own totals — a formatting pass on data already collected, not new instrumentation.

## 13. Optional — `claude_api`/`claude_cli` hint providers, now that the Gatekeeper exists

**Explicitly optional** (PRD 7's own "Explicitly out of scope" section) — not required for this layer's milestone, not required for the game itself (`template`/`ollama` already suffice at zero tokens per Table 21). Build only if time permits, after everything above is done and watched.

- [ ] `ClaudeApiHintProvider.generate(...)` — a real Anthropic API call, routed through `ApiGatekeeper.execute()`, token usage logged for `observability/cost.py` to actually aggregate something non-zero.
- [ ] `ClaudeCliHintProvider.generate(...)` — a real `claude -p` subprocess call, same Gatekeeper routing.
- [ ] Remove the `NotImplementedError` stubs and their "until PRD 7's `policy/gatekeeper.py` exists" docstring language once built — same "delete the forward-reference in the same commit that closes it" discipline as `RULE-27-REMOVE-AT-PRD-4`.
- [ ] Test: a rejection path when the Gatekeeper itself blocks the call (simulated quota/rate-limit exhaustion) — the hint provider degrades to raising or falling back, not silently hanging.

## 14. Cleanup and final verification

- [x] Every new/touched module re-checked against the 150-line house cap.
- [x] Full `uv run pytest` — green, 418 passed, 99.87% coverage (matching every prior layer's own bar, not just the guide's 85% floor; the two remaining lines are `gmail_sender.py::get_service`'s real OAuth call, deliberately undoctored — no live Gmail credentials exist in this environment, documented in the test file's own module docstring rather than mocked to pad the number).
- [x] `uv run ruff check .` — clean.
- [x] `check_config.py` — still passing; if `GameConfig.from_dict` was extended to read `network_and_league`/`rate_limiter_gatekeeper`, confirm no existing field's validation regressed.
- [x] `rule-auditor` run against the full rule set this layer owns (8, 9, 20, 28-38, 39, 40, 41-45, 49-52, 54, 55) — explicit sign-off gate before commit, same discipline as PRD 6's own closing pass; flagged which rules are genuinely code-verified vs. administrative (as expected), plus two real, non-fatal wiring gaps: no automatic end-of-game sequence (§6 line 65, above) and the capture-claim/response protocol (rules 21/22, built in PRD 3/6, not this layer) still unwired from `take_turn()`/`build_server()`. Both documented in `PRD-7-reporting-shell.md`'s Retrospective, neither built in this pass.
- [x] Sanity-check sabotage, at minimum: (a) temporarily let the Gatekeeper's `execute()` skip a gate, confirm the corresponding test catches it, revert; (b) temporarily tamper a Replay Viewer fixture log, confirm `TAMPERED` fires, revert; (c) temporarily widen `SCOPES` to `gmail.modify`, confirm the literal-equality guard catches it, revert; (d) temporarily make `run_peer_audit` call `run_mutual_audit` internally (i.e. accidentally self-audit instead of peer-audit), confirm §6's own bilateral adversarial test catches it, revert — the one sabotage in this layer most worth actually running, since it's the exact failure mode that would make the "bilateral" claim silently false.
- [x] `git log --all --full-history -- '*credentials*' '*token.json*' '*.env'` — must return nothing, re-run now that real OAuth files may have touched the working tree during development.
- [x] Update `PRD-7-reporting-shell.md`'s status line to "Built & verified" with an honest retrospective section, same as every prior PRD's own closing discipline — note anything found via construction that wasn't anticipated here, and note explicitly which rules stayed **[admin]**/**[honesty]** rather than becoming fully **[code]**-verified, matching PRD 6's own "don't let the status line overclaim" correction.
- [x] Update `TODO.md`'s own PRD 7 entry.
- [x] Verify the README's six mandatory academic-report sections (ch. 9.4.2) are all present: Dec-POMDP model description; FastMCP orchestration dilemmas (turn management, network-failure handling, Orchestrator/Gatekeeper roles); the decision-making mechanism actually implemented; RL learning curves (only if RL was built — Optional Layer 8, honestly reported as not built); the mandatory Live GUI + Replay-App-showing-`Verified OK` screenshots (**gap**: `README.md` didn't exist at all before this closing pass — created here with all six sections, but the actual screenshot image files still need a human with a display to run `scripts/watch_prd7_live_gui.py`/`watch_prd7_replay.py` and capture them, marked with an explicit `TODO:` in the README itself); the link to the companion (thief) repo (**gap**: real URL not yet confirmed, placeholder marked in README).
- [x] Commit only after all of the above — matching every prior layer's own closing rule.
