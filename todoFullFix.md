# todoFullFix.md — execution checklist for `FULLFIX.md`

Prospective — nothing below is built yet. Doc-only until this checklist itself has been reviewed, matching this repo's own PRD → TODO → execute discipline (see `TODO4-revision2.md` for the precedent this mirrors at finer grain). Each item is individually completable and checkable. Sections are lettered A–H; within a section, items are sequenced so later ones depend on earlier ones in the same section. Cross-section dependencies are noted per the table in `FULLFIX.md`/the approved plan: **A** is foundational; **B** depends on A's test fixtures; **C** is independent of A/B but the largest; **D** depends on C; **E** depends on C's belief-update call sites; **F**/**G** are documentation-only and independent; **H** is the final gate over everything.

---

## A. Config schema migration — Appendix B nested names become the source of truth

### A0. Baseline
- [x] Run `check_config.py config/shared/config_dev_g01.json`, confirm the current 31/31 pass, and save the output as the "before" baseline to compare against after the reshape
- [x] Re-grep the repo for `schema_version`/`agreed_between`/`board_and_agents`/etc. immediately before starting, to catch any drift since the audit that grounded this plan

### A1. Rewrite `.claude/skills/spec-guard/references/PARAMETERS.md`
- [x] Table 13 → nested under `board_and_agents` (`grid_size`, `num_agents`, `thief_start`, `cop_start`, `axis_origin_corner`, `axis_start_index`)
- [x] Table 14 → nested under `world` (`map_area`, `hint_max_words`) — confirm `arena` maps to `world.map_area`
- [x] Table 15 → nested under `movement_and_barriers` (`move_set`, `max_barriers`, `max_moves`, `survival_threshold`)
- [x] Table 16 → nested under `pheromones` (`pheromone_center_intensity`, `pheromone_decay`, `pheromone_grid_size`)
- [x] Table 17 → nested under `scoring` (`capture_cop`, `capture_thief`, `survival_cop`, `survival_thief`, `tie_score`, `technical_loss`)
- [x] Table 18 → nested under `network_and_league` (`num_games`, `diversity_reward`, `min_games_to_pass`, `token_budget_per_series`, `max_games_per_team`) — plus `response_timeout_sec`/`watchdog_timeout_sec`'s actual home confirmed here
- [x] Table 19 → nested under `rate_limiter_gatekeeper` (`requests_per_minute`, `concurrent_requests`, `retry_backoff_sec`, `max_retries`, `queue_depth`)
- [x] Add `schema_version`/`agreed_between` as new top-level entries with the constant/negotiable status p.129's example implies
- [x] Add the Status-column semantics (constant / minimum / negotiable) verbatim per p.155's three-way definition, if not already stated this precisely
- [x] Rewrite the trailing "Quick reference" flat JSON block into the new nested shape

### A2. `GameConfig.from_dict()` migration (`src/cop/shared/config.py`)
- [x] Rewrite `from_dict()` to read the nested Appendix B paths, populating the *existing* internal dataclass field names (translation-layer-only, per the plan's confirmed decision — internal names are not renamed)
- [x] Confirm all 4 private validator helpers (`_positive_int`, `_positive_number`, etc.) are unchanged — they're name-agnostic
- [x] Decide and implement `schema_version`/`agreed_between` handling: store as new `GameConfig` fields (recommended, since later audit/reporting needs may want them) vs. validate-and-discard
- [x] Rebuild `tests/unit/test_config.py`'s `_full_config()` helper to construct nested dicts instead of flat ones
- [x] New test: `from_dict()` on a flat (old-shape) JSON fails with a clear error rather than silently defaulting — proves the migration doesn't mask a real config mistake
- [x] New test: round-tripping Appendix B's own literal p.129 example through `from_dict()` produces a `GameConfig` whose every value matches exactly

### A3. Config file reshape
- [x] Rewrite `config/shared/config_dev_g01.json` into the nested Appendix B shape, preserving every current locked value (7×7, 14 barriers, 35-step ceiling, 0.9/0.10/5×5 scent, 20/5 capture, 5/10 survival, etc.)
- [x] Add `"schema_version": "1.2"` and `"agreed_between": [...]`
- [x] Diff every value against the pre-reshape file to confirm zero accidental drift
- [x] Confirm the filename itself needs no change — `config_dev_g01.json` already matches Table 20's `config_<game_id>_g<NN>.json` convention; document why in a short comment/commit note rather than silently leaving it unexplained

### A4. `check_config.py` updates
- [x] Audit every alias in `TABLE` against the book's exact new names; add missing ones (`pheromone_center_intensity`, `response_timeout_sec` vs. current `response_timeout_seconds`, `watchdog_timeout_sec` vs. `watchdog_threshold_seconds`, and confirm `capture_thief`/`survival_cop`/`survival_thief`/`tie_score`/`technical_loss` are covered)
- [x] Decide and implement whether `schema_version`/`agreed_between` get validated by `check_config.py` at all (they're metadata, not a game parameter in Appendix F's numeric sense) — document the decision either way
- [x] Re-run against the reshaped file, confirm full pass (31/31, or 33/33 if the two new fields are added to the checked set)
- [x] New rejection test: a file missing a mandatory nested field still fails clearly — proves the validator didn't get quietly weaker during the migration (this repo's "write at least one test per layer that proves rejection" rule)

### A5. Documentation sweep
- [x] `PLAN.md` — every prose reference to the old flat names corrected, including §7's repo-layout config line
- [x] `PLAN.md:127`'s stray `config/game.json`/`rate_limiter_gatekeeper` reference reconciled with the actual filename
- [x] `PRD/PRD-1-base-logic.md` — flat-name references corrected
- [x] `PRD/PRD-3-blind-strategy.md` — flat-name references corrected
- [x] `PRD/PRD-4-language-and-scent.md` — flat-name references corrected (coordinate with Section C's Revision 3 rewrite of the same file — one pass, not two conflicting edits)
- [x] `PRD/PRD-5-cloud-exposure.md` — flat-name references corrected
- [x] `TODO.md`/`TODO1.md`/`TODO3.md`/`TODO4.md` — currently load-bearing prose corrected; historical checklist entries can stay as literal history
- [x] `WIRE-CONTRACT.md` — flat-name references corrected (coordinate with Section C/D's rewrite of the same file)

### A6. Section verification
- [x] `uv run pytest` green
- [x] `uv run ruff check .` clean
- [x] `check_config.py` full pass on the reshaped file
- [x] `rule-auditor` pass focused on rules 11/12 against the reshaped schema

---

## B. Private config → `config/game.toml`, TOML, all six sections

### B0. Baseline
- [x] Re-confirm zero `config/game.toml` exists and `private_config.py`'s current JSON-only, single-section behavior, immediately before starting

### B1. New private config file
- [x] Create `config/game.toml` (confirmed path from p.126: sibling to `config/game.json`'s conceptual location — this repo's real shared file is `config/shared/config_dev_g01.json`, so place the private file at the repo-root-relative path the book uses, `config/game.toml`, and confirm it doesn't collide with the existing `config/private/`/`config/shared/` split — decide whether `config/private/` as a directory still makes sense once there's one canonical file, or whether the file lives directly under `config/`)
- [x] `[game]`: `group_name`, `group_id`, `sub_game_number`, `members`, `repos` (cop/thief URLs)
- [x] `[network]`: `my_port`, `opponent_url`, `turn_timeout_seconds`
- [x] `[strategy]`: `thief_class`/`police_class`, commented out/optional per the book's own example
- [x] `[trash_talk]`: `provider`, `every_n_steps` — migrate the current values from `config/private/trash_talk_dev.json`
- [x] `[llm]`: `model`, `step_deadline_seconds`
- [x] `[email]`: `recipient`, `mode`
- [x] Top-level `version = "1.10"` per the book's own example

### B2. `private_config.py` rewrite
- [x] Rewrite `PrivateConfig` to hold all six sections (decide: nested dataclasses per section, or one flat merged dataclass — document the choice)
- [x] Switch the loader from `json.loads` to `tomllib.load` (stdlib, `>=3.11`, binary-mode file read — `tomllib` requires bytes, not text)
- [x] Update `from_file()`'s default path from `config/private/trash_talk_dev.json` to `config/game.toml`
- [x] Confirm `.provider`/`.every_n_steps` stay accessible the same way at the two existing call sites (`orchestrator.py`, `orchestrator_turn.py`) — no other change needed there
- [x] Add `.opponent_url`, `.my_port`, `.turn_timeout_seconds` accessors

### B3. Wire `opponent_url` into the Orchestrator
- [x] Make `Orchestrator.take_turn(peer_url: str)`'s `peer_url` optional, defaulting to `self.private_config.opponent_url` when not passed
- [x] Confirm every existing test that passes `peer_url` explicitly is unaffected (additive change only)
- [x] New test: `take_turn()` called without an explicit `peer_url` argument uses the private config's `opponent_url`

### B4. Old file retirement
- [x] Delete `config/private/trash_talk_dev.json` now that `config/game.toml` supersedes it (keeping both would reintroduce the exact drift this pass exists to close) — confirm this decision, don't leave two live sources of the same setting
- [x] Rewrite `tests/unit/test_private_config.py`'s fixtures from JSON to TOML

### B5. Documentation
- [x] `PRD/PRD-5-cloud-exposure.md`'s "a human, operational step, not something this layer's code automates" framing corrected to point at `[network].opponent_url`
- [x] `PLAN.md` §7 repo layout's `config/private/ peer.json` line corrected to `config/game.toml`
- [x] Decide and document whether `config/game.toml` is gitignored: re-check p.157's Table 20 (the four *attached* files are declaration/config/log/result JSONs — `game.toml` is not among them) against p.126-127's "never crosses the network, never signed" framing — resolve whether that means "committed to your own repo but never sent to the opponent" or "not committed at all"; document the decision in `.gitignore` and in this doc, don't leave it ambiguous
- [x] `WIRE-CONTRACT.md` — note `opponent_url`'s new canonical home if relevant to the teammate negotiation

### B6. Section verification
- [x] `uv run pytest` green
- [x] `uv run ruff check .` clean
- [x] Confirm zero new third-party dependency in `pyproject.toml` (stdlib `tomllib` only)
- [x] `rule-auditor` pass confirming `config/game.toml` is never compared for byte-identity against the opponent's copy (staying true to "private per peer, not negotiated")

---

## C. Scent-map wire redesign — PRD 4 "Revision 3"

### C0. Design the new tool shape
- [x] Decide the wire-serializable shape for `dict[Position, float]` (e.g. a list of `[col, row, value]` triples) and document the rationale
- [x] Decide the new tool's name (e.g. `receive_scent_map`) — confirm it reads as "opponent shares its own scent field with me," matching ch. 6.4's framing
- [x] Decide pull vs. push: recommend a pull-style tool call (the requesting side's client actively calls the peer's tool, matching ch. 6.5's "the client uses a Tool... to gather data" and staying symmetric with the existing `receive_hint` pattern) — confirm this doesn't disturb PRD 3-5's existing turn sequencing
- [x] Decide scope: full board (`ScentField`'s complete internal state) vs. a windowed sample — recommend the full field, since ch. 4.4's worked example reads near AND far cells, including an explicit distant zero, not just a local window
- [x] Confirm this requires a new public accessor on `ScentField` (its internal `_levels` is currently private) rather than reaching into a private attribute from outside the class

### C1. `ScentField` — new public accessor
- [x] Add `ScentField.full_field() -> dict[Position, float]` (name TBD) returning the complete state, board-clipped
- [x] Decide sparse vs. dense representation (recommend sparse — only nonzero cells — for wire efficiency; receiver zero-fills the rest, matching `sample()`'s existing convention of treating absence as zero)
- [x] Test: `full_field()` matches internal state exactly after several `advance()` calls
- [x] Test: a cell that's genuinely never been near any deposit is correctly absent (zero) from the sparse output, and a receiver reconstructing from it treats missing keys as zero

### C2. Wire serialization
- [x] Implement a small, focused serialization helper converting `ScentField.full_field()` ⇄ the wire shape decided in C0 (decide location — likely `tools/` alongside the MCP client/server, or a new small module)
- [x] Test: serialize → deserialize round-trips exactly, float precision preserved, no coordinate corruption
- [x] Test: "grep the wire" style check — the serialized payload contains only numeric scent data, nothing else from `GameState` leaks through (own claimed position, barriers, etc.) — same discipline as PRD 4's original coordinate-leak sweep, applied to the new channel

### C3. MCP server/client changes
- [x] Add the new tool to `build_server()` in `src/cop/tools/mcp_server.py`, exposing the sender's own `ScentField.full_field()` via a new callback (mirroring the existing `on_receive`/`on_hint` injection pattern)
- [x] Add the corresponding client function to `src/cop/tools/mcp_client.py` (e.g. `request_scent_map(url) -> dict[Position, float]`)
- [x] Narrow `receive_hint`'s signature back to `receive_hint(text: str) -> dict` — remove `scent_report`
- [x] Narrow the ack shape to `{"accepted": bool, "word_count": int}` — remove `scent_word_count`
- [x] Update `send_hint` in `mcp_client.py` to match the narrowed signature

### C4. Orchestrator wiring
- [x] Update `Orchestrator.send_to_peer()` — drop the `scent_report` parameter
- [x] Update `take_turn()` in `orchestrator_turn.py` to call the new scent-map client function instead of `generate_scent_report`, and decide whether it happens in the same turn as the hint exchange or as a distinct step (recommend same turn, matching the existing milestone's "one turn's exchange" framing)
- [x] Rewrite `_on_hint_received` — drop the `scent_report`/`is_no_scent_report` gating entirely; keep the tactical-hint `text` word-limit gating unchanged
- [x] Add a new server-side handler for the scent-map tool call, returning data rather than accepting it
- [x] Update trace logging: drop `scent_report` from `"sending_hint"`/`"hint_received"` events; add new events for the scent-map exchange (e.g. `"scent_map_sent"`/`"scent_map_received"`)

### C5. `reasoning/hint.py` — retire the language-based mechanism
- [x] Delete `dominant_scent_direction`
- [x] Delete `generate_scent_report`
- [x] Delete `is_no_scent_report` and the `_NO_SCENT_REPORT` sentinel
- [x] Confirm `interpret_hint` is untouched — still needed for the tactical hint only
- [x] Re-check `reasoning/hint.py`'s line count after the deletions (well under the 150-line cap expected)

### C6. `memory/belief.py` — numeric scent update
- [x] Design `update_from_scent_map(scent_data: dict[Position, float], board: Board) -> None`, replacing `update_from_scent_report(focal_point, board)` — consumes real per-cell data, not a single re-quantized `Position`
- [x] Decide the exact update math in coordination with Section E's reliability-coefficient/Bayesian redesign, so this isn't built twice (recommend deferring the final math decision to E0, building this method's plumbing/shape here, its actual formula there)
- [x] Remove or repurpose the `_SCENT_REPORT_BOOST` constant per that same coordination
- [x] Test: given a real `ScentField` trail, `update_from_scent_map` shifts belief toward the true region using actual τ magnitudes — proves the new channel uses real numbers, not a degraded quadrant guess in disguise

### C7. Rule 27 legal review — explicit sign-off before treating the design as final
- [x] Write a short, explicit note (in `FULLFIX.md` or a new `PRD-4-revision-3-scent-tool.md`) walking through why a `dict[Position, float]` scent-map response doesn't violate rule 27, citing ch. 4.4's worked example directly
- [x] Run `rule-auditor` specifically against rules 26/27 on the new tool's shape *before* proceeding further — matches this project's precedent of raising exactly this kind of fatal-rule-adjacent question explicitly (Revision 1's own "resolving the rule 26/27 tension" note) rather than deciding it alone
- [x] Resolve any concern `rule-auditor` raises (redesign or document explicit rationale) before starting C8

### C8. Test suite rebuild
- [x] Retire/rewrite `tests/unit/test_hint.py`'s scent-specific tests — the surviving concerns move to testing `ScentField.full_field()`/the C2 serialization helper
- [x] Rewrite `tests/unit/test_belief.py`'s `update_from_scent_report` tests for `update_from_scent_map`
- [x] Rewrite `tests/unit/test_belief_deception.py`'s corroboration milestone test for the new numeric channel
- [x] Rewrite `tests/unit/test_orchestrator_take_turn.py`'s scent-report assertions for the new tool-based exchange
- [x] Rewrite `tests/unit/test_mcp_server.py`'s `receive_hint`/scent tests for the narrowed signature plus the new tool
- [x] Rewrite `tests/unit/test_mcp_client.py`'s `send_hint`/scent tests correspondingly
- [x] Update `tests/unit/test_orchestrator.py`, `test_timeout_asymmetry.py`, `test_orchestrator_watchdog.py`, `test_orchestrator_network_hardening.py`'s `receive_hint(text, scent_report)` stub fixtures to the narrowed 1-parameter signature
- [x] Update `tests/unit/test_prd6_missing_wire_channels_guard.py`'s "current wire surface" baseline assertion for the new signature (still guards the barrier-declaration/capture-claim gaps)
- [x] Rewrite `tests/unit/test_prd6_scent_audit_guard.py` — the `RULE-19-SCENT-AUDIT-AT-PRD-6` guard's framing changes (the sender's real `ScentField` is now exposed directly rather than a "declared reading," but the underlying risk — an unhashed value until PRD 6 — survives, just needs the framing corrected)
- [x] Rewrite `scripts/watch_prd4_language.py`'s corroboration demo section for the new tool-based flow
- [x] Update `tests/integration/_helpers.py`/`_server_process.py`'s scent-related CLI scaffolding for the new tool

### C9. Documentation
- [x] `WIRE-CONTRACT.md` — replace the `scent_report` field documentation with the new tool's name/signature/return shape; remove the "Not book-mandated" flag (now book-faithful) and the "always-informative pacing" note (dissolved per Finding 1)
- [x] `PRD/PRD-4-language-and-scent.md` — add a full "Revision 3" section (bug/gap, book citation, fix, test rebuild, sanity-check-by-sabotage, "Built & verified" once done) — preserve Revision 1/2's design history rather than deleting it, matching this repo's existing discipline
- [x] `TODO.md`'s PRD 4 entry — add the Revision 3 line once built
- [x] `PLAN.md`'s PRD 4 section — update the milestone description if it still references the language-based mechanism

### C10. Section verification
- [x] `uv run pytest` green
- [x] `uv run ruff check .` clean
- [x] 100% coverage maintained
- [x] Sanity-check sabotage: temporarily degrade the new tool to return a coarse quadrant-only signal instead of real per-cell data, confirm the rebuilt belief-update test (C6) fails — proves the test exercises real numeric data, then revert cleanly
- [x] Final `rule-auditor` pass on the whole section (26/27/23, I6/I9)

---

## D. `WIRE-CONTRACT.md` — ch. 4.5's negotiation ceremony

- [x] Add a "Scent-model negotiation ceremony" section citing ch. 4.5 (p.47) directly
- [x] Include the concrete numeric worked example to exchange and hash (centre cell τ=0.9 → 0.9·(1−0.10)=0.81 after one decay round)
- [x] Document the SHA-256 lock of "the agreed formula together with the numeric example" as a PRD 6 action item, cross-referenced from here
- [x] Add the explicit recommendation to offer the teammate the `ScentField` implementation's source directly, not only a written description
- [x] Update "PRD 6 will add more of this" to include the new scent-map tool (Section C) as a fourth wire-surface item needing negotiation, alongside barrier declaration/capture claim-response/commit-reveal envelope
- [x] Update the Status log to reflect that this pass changes the wire shape materially (unlike PRD 4 Revision 2) — treat it as a new proposal to the teammate, not a formality
- [x] Full read-through for internal consistency after Section C's rewrite — confirm no stray `scent_report` references survive
- [x] Add a short "why this changed" changelog note at the top for a teammate re-reading an earlier draft
- [x] Re-read the finished doc end-to-end against the actually-shipped code, not the aspirational design
- [x] Confirm `PLAN.md`'s cross-reference to `WIRE-CONTRACT.md` (§7) still describes it accurately

---

## E. Belief map — genuine Bayes update, reliability coefficient, zero-belief barriers

### E0. Design
- [x] Decide where the reliability coefficient lives: a local, code-level constant (the book gives the *concept*, not a specific number) exposed via config for tunability, vs. a literal — document the choice and why it isn't an Appendix B field (the book doesn't specify one there)
- [x] Write out the exact Bayesian formula before coding: `P(state|evidence) ∝ P(evidence|state) · P(state)`, with the likelihood term parametrized by the reliability coefficient (e.g. `P(evidence|state=focal)=reliability`, `P(evidence|state=elsewhere)=(1−reliability)/N`) — matches this repo's "design questions answered in the PRD, not in code" rule

### E1. `BeliefMap` rewrite (`src/cop/memory/belief.py`)
- [x] Rewrite `update_from_hint` to the genuine Bayesian posterior update from E0, replacing the hardcoded `_HINT_BOOST` multiplicative factor
- [x] Finalize `update_from_scent_map`'s math (plumbing built in C6) using per-cell likelihoods derived from real τ values
- [x] Add barrier awareness: accept a `Barriers`/`BarrierSet` reference (constructor parameter or a new method)
- [x] Zero out barrier cells' belief explicitly, at construction and whenever the barrier set changes
- [x] Rewrite `most_likely_cell()` to exclude barrier cells from the argmax
- [x] Revisit the "no cell ever hits exactly 0" design comment/invariant — carve out an explicit, documented exception for barrier cells only
- [x] Confirm renormalization after zeroing barrier cells redistributes mass correctly, doesn't just vanish it

### E2. Tests
- [x] Test: a low reliability coefficient shifts belief less than a high one for the same hint (proves the coefficient is load-bearing)
- [x] Test: rebuild the corroboration milestone (lying hint + real scent-map data) against the new math, confirming truth still wins
- [x] Test: a barrier cell never wins `most_likely_cell()`, constructed so it *would* win under the old unfiltered argmax
- [x] Test: barrier cells sit at exactly 0.0, every non-barrier cell stays > 0.0, distribution still sums to 1
- [x] Test: `BeliefMap.uniform()` with barriers already known seeds barrier cells at 0 from construction, not only after a later update
- [x] Sanity-check sabotage: revert the reliability coefficient to a flat constant, confirm the reliability-sensitivity test fails; revert the barrier exclusion, confirm the barrier-cell test fails; revert both cleanly and confirm green again

### E3. Documentation
- [x] Rewrite `memory/belief.py`'s module docstring to describe the genuine Bayesian update, reliability coefficient, and zero-belief barriers, replacing the old "simpler than full Bayesian, defensible for this layer" framing
- [x] `PRD/PRD-4-language-and-scent.md` (or wherever belief-map math lives) gets a short note distinguishing "book-required" from "this repo's own legitimate enhancement," if anything non-book-mandated remains after this rewrite — state plainly either way, don't leave it implicit
- [x] `PARAMETERS.md`/`FULLFIX.md` record the reliability coefficient's status (config-exposed local design choice, not an Appendix B field)

### E4. Section verification
- [x] `uv run pytest` green
- [x] `uv run ruff check .` clean
- [x] 100% coverage maintained
- [x] `rule-auditor` pass on I6 (reliability coefficient sourced correctly, no magic number) and I9 (belief-map's untrusted-input handling unaffected)

---

## F. Rule 25's negotiated LLM-move exception — documentation only

- [x] Add a short paragraph to `PLAN.md` (near the architecture invariants or PRD 3's `CopBrain` section) documenting rule 25's negotiated exception, citing ch. 6.5 (p.65-66) directly
- [x] State explicitly that this repo does not currently exercise the exception — `CopBrain`/`_pick_move` stays algorithmic-only by default — and adopting it later would need explicit, written, mutual agreement with the teammate first
- [x] Cross-reference from `WIRE-CONTRACT.md`'s negotiation-items list

---

## G. Table 20's canonical file-naming convention — record it, don't build it yet

- [x] Add `declaration_<game_id>.json`/`result_<game_id>.json` to `PLAN.md`'s repository-layout/sequence section, confirming `config_<game_id>_g<NN>.json`/`log_<game_id>_g<NN>.json` already match
- [x] Add a one-line pointer to Table 20 in whichever future PRD doc governs declaration/results reporting (PRD 7, per `PLAN.md`'s own layer list) so the naming isn't reinvented later
- [x] Verify (don't change) that `CLAUDE.md`'s Commands section already uses the correct config/log naming pattern

---

## H. Full re-verification — the final gate

- [x] Full `uv run pytest` — green, 100% coverage, across all sections combined
- [x] `uv run ruff check .` — clean
- [x] `check_config.py` against the final reshaped config file — full pass
- [x] Every touched module re-checked against the 150-line house cap
- [x] `rule-auditor` full sweep: rules 11/12 (config), 23/26/27 (scent + ceremony), 25 (documented exception, no violation introduced), I6/I9 throughout
- [x] `git diff` review of every changed file — confirm nothing unrelated crept in across a pass this large
- [x] Secret sweep (`git log --all --full-history -- '*credentials*' '*token.json*' '*.env'`) — confirm still clean, especially given `config/game.toml` now holds email/group/repo data
- [x] `WIRE-CONTRACT.md`'s status log updated to reflect the full scope of change, ready to send to the teammate as a new proposal
- [x] `FULLFIX.md`'s findings cross-checked one final time against the actually-shipped code, not the plan — note any deviations honestly, matching this repo's "Built & verified" discipline
- [ ] Commit sequenced per section (recommend: A, B, C+D together, E, F+G together, H as the final wrap) rather than one giant commit — decide the exact grouping at execution time based on how cleanly each section's tests pass in isolation, but commit only after each section's own verification passes, never all at the end
