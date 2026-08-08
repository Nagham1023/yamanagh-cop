# TODO — Cop Repo

Running task list, per rule 50. Full project roadmap, not just the current layer — each item traces to a rule in `spec-guard/references/RULES.md` or a build/test/verify step from `PLAN.md` §5. Definition of done for any item below: CLAUDE.md's six-item checklist (milestone watched by a human, tests + ≥85% coverage, `ruff check` clean, `spec-guard` clean, docstrings present, committed with the PRD updated).

## PRD 1 — Base logic — **DONE**

- [x] rule 12 — minimums (board size, barrier quota, ceilings) raised only by agreement, never lowered
- [x] rule 13 — orthogonal moves only (`domain/movement.py`)
- [x] rule 14 — diagonals rejected (`domain/movement.py`)
- [x] rule 46 — barrier on thief's cell = capture (`domain/capture.py`)
- [x] rule 47 — thief with zero legal moves = capture (`domain/capture.py`)
- [x] rule 48 — score every end scenario per Table 17 (`domain/scoring.py`)
- [x] invariant I6 — no magic numbers, everything from config (`shared/config.py`)
- [x] build: `Board`/`Position` geometry
- [x] build: movement legality (`DELTAS`, `apply_move`)
- [x] build: `BarrierSet` — quota + one-cell-adjacency
- [x] build: capture detection (coordinate, barrier, encirclement)
- [x] build: `score_outcome` for capture/survival/technical-loss
- [x] build: `determine_outcome` end-condition evaluator
- [x] build: `GameConfig` loader, fails loudly on missing fields
- [x] config: `config/shared/config_dev_g01.json` written, validated 31/31 vs Appendix F
- [x] tests: 44 tests written, incl. rejection cases (diagonal, over-quota, over-distance)
- [x] tests: ≥85% coverage — hit 100%
- [x] `ruff check` clean (scoped away from `.claude/` skill scripts)
- [x] milestone watched end-to-end (`scripts/watch_prd1.py`)
- [x] `rule-auditor` run — zero fatal violations
- [x] `PRD/PRD-1-base-logic.md` written
- [x] `TODO1.md` — critical re-review, found and fixed a real bug (off-board barrier silently consumed quota) plus 3 coverage/validation gaps; 44→52 tests
- [x] four narrated demo scripts + 2 backing tests (52→54); run commands below
- [x] commit PRD 1 to git — standalone repo initialized, first commit `d95381b`

**Demo scripts (run from repo root):**
```bash
uv run python scripts/watch_normal_game.py         # positions change by one, turn by turn
uv run python scripts/watch_diagonal_move.py        # diagonal rejected, orthogonal accepted
uv run python scripts/watch_barrier_placements.py    # 14 placements from config, declared, 15th refused
uv run python scripts/watch_capture_ends_game.py     # cop lands on thief -> GAME OVER, scored
uv run python scripts/watch_prd1.py                  # the full PRD 1 milestone checklist, all in one
```

## PRD 2 — FastMCP infra over localhost — **DONE**

- [x] rule 1 — cop and thief run in two completely separate processes
- [x] rule 2 — no shared memory/variables between the two sides, ever
- [x] rule 3 — `Orchestrator` as the single entry point to every subsystem
- [x] rule 4 — proper state machine manages game states
- [x] rule 5 — illegal state transitions rejected, not absorbed
- [x] rule 6 — deadline tracker on every wait for the opponent
- [x] rule 7 — watchdog monitors the process, extracts data on crash — fixed a real gap found in retrospective review: the watchdog object existed and was unit-tested but nothing drove `.check()` during real server operation; `run_as_server()` now runs a daemon poll loop, and `receive_position` feeds it real heartbeats
- [x] build: `tools/mcp_server.py` — FastMCP server, `@mcp.tool` surface
- [x] build: `tools/mcp_client.py` — calls into the peer's server
- [x] build: `orchestrator.py` skeleton wiring config/domain/tools together
- [x] build: state machine states + transition table (`planner/`)
- [x] build: deadline tracker (`planner/`)
- [x] build: watchdog process (`planner/`)
- [x] build: `observability/trace.py` log manager (Fig. 12's fifth wire, added mid-layer per PRD Design Question 4)
- [x] build: two-process local test harness (spawn both roles, localhost)
- [x] carried from PRD 1: enforce barrier "forgo move" once turn state exists — closed in PRD 3, `reasoning/state.py`'s `GameState.apply`
- [x] test: geometric message from A decoded correctly by B (milestone)
- [x] test: illegal state transition is rejected, not absorbed
- [x] test: killing one peer causes the other to hit its deadline and exit cleanly with a log
- [x] test: watchdog fires and extracts data on a forced crash
- [x] test: the two processes share no importable live state
- [x] milestone watched end-to-end by a human
- [x] `rule-auditor` run, zero fatal/non-fatal violations (rules 1–7, I6, I9, I10 all CLEAN)
- [x] `PRD/PRD-2-fastmcp-infra.md` written; commit

**Demo script (run from repo root):**
```bash
uv run python scripts/watch_prd2_roundtrip.py   # two OS processes, round-trip, illegal transition rejected, killed-peer -> clean technical loss with log
```

## PRD 3 — Blind strategy — **DONE**

- [x] rule 25 / invariant I7 — move decision is never delegated to the LLM (first move-deciding code in the repo — nothing to check this against before now)
- [x] build: `BrainBase` extension contract (`_pick_move`, `_decide_move`) — `reasoning/brain_base.py`
- [x] build: Manhattan-distance heuristic for the cop — `reasoning/cop_brain.py`
- [x] build: `greedy_thief_move` — prefers cells with more escape routes; deliberately a **test/demo fixture**, not a `ThiefBrain` (Table 22: `thief_class` is the teammate's own repo's concern) — `tests/support/greedy_thief_mover.py`, outside `src/cop/`
- [x] build: cop `_decide_move` — barrier policy, never walls the cop off from the thief
- [x] build: step-ceiling respected via `reasoning/subgame.py`'s local turn loop calling `domain/end_conditions.determine_outcome` every round
- [x] build: `COMPUTING_MOVE` state added to the state machine ahead of `SENDING`
- [x] build: `Orchestrator.take_turn()` — wires the brain into the real peer connection (kept deliberately separate from algorithm-correctness testing)
- [x] test: given a known target, shortest path computed and executed unattended (milestone) — `reasoning/subgame.py`'s `run_local_subgame`, no network
- [x] test: cop's barrier policy never traps the cop itself
- [x] test: thief fixture measurably prefers higher-escape-route cells
- [x] found + fixed a real bug: the barrier heuristic could block the cop's own best path, causing a permanent oscillation — fixed by excluding the cop's own preferred next step from barrier candidates (which also made a separate self-trap check provably-dead code, removed rather than kept untested)
- [x] milestone watched end-to-end by a human
- [x] `rule-auditor` run, zero fatal violations
- [x] `PRD/PRD-3-blind-strategy.md` written; commit

**Demo script (run from repo root):**
```bash
uv run python scripts/watch_prd3_brain.py   # local pursuit (static + moving target) + one real take_turn() round-trip
```

## PRD 4 — Language and scent — **DONE**

- [x] rule 23 — scent-emission model cryptographically locked pre-game (model made config-driven and `check_config.py`-checkable here; the actual pre-game locking ceremony is PRD 6's Step-0)
- [x] rule 26 — in-game communication is free natural language only
- [x] rule 27 — no numeric position protocol (removed PRD 2's bare-coordinate scaffolding — `receive_position`/`send_position` deleted entirely)
- [x] build: Table 14 params (arena, hint word limit) wired from config
- [x] build: scent emission + decay model per Table 16 constants (`memory/scent.py`)
- [x] build: belief-map update from scent + hint (`memory/belief.py`; multiplicative reweighting, not a full Bayesian posterior — documented as a defensible choice for this layer)
- [x] build: LLM hint generation, `template` mode as zero-token default (`tools/hint_providers.py`, `ollama` also implemented at zero API cost; `claude_api`/`claude_cli` deliberately interface-only until PRD 7's Gatekeeper)
- [x] build: `Intent` truth/lie flag on outgoing hints, locally recorded via `trace.log("hint_generated", intent=...)`
- [x] build: hint word-limit enforcement in the LLM system prompt (`OllamaHintProvider.system_prompt`), backstopped by a hard Python truncation
- [x] test: grep the wire — no coordinates survive anywhere in an outgoing hint (`test_hint.py`'s exhaustive sweep across all board positions × both intents)
- [x] test: belief map is a genuine probability distribution (sums to one) after every update
- [x] test: a known-false hint measurably shifts belief in the wrong direction (milestone) — `test_belief_deception.py`
- [x] test: scent constants match Table 16 exactly, sourced from `GameConfig` not literals, exposed for pre-game locking
- [x] found + fixed a real gap: the PRD 3 seam had *three* non-seam sites once belief-driven `target_pos` landed (`orchestrator.py`'s init and `orchestrator_turn.py`'s per-turn refresh), not the one originally planned — caught by `test_prd4_seam.py` itself, documented in the PRD's Design Question 3
- [x] milestone watched end-to-end by a human (`scripts/watch_prd4_language.py`)
- [x] `rule-auditor` run against rules 23/26/27 and I6/I9, zero fatal violations
- [x] `PRD/PRD-4-language-and-scent.md` written; commit
- [x] **Revision 1**: a direct re-read of the book (ch. 4.2–4.4, not just PLAN.md's paraphrase) found the scent model wrong on three counts — point deposit instead of Figure 4's radial 5×5 kernel, decay/emission composed as two separate non-additive calls instead of `τ(t+1)=max(0,(1-ρ)τ(t)+Δτ)` in one step, and self-only trail instead of each side reading its *opponent's* scent field. Fixed per `PRD-4-language-and-scent.md`'s "Revision 1" section and `TODO4-revision.md`: `ScentField.advance()` replaces `emit()`+`decay()`; a new always-truthful `scent_report` field rides alongside the tactical hint on the same wire message (rule 26/27-safe — still plain natural-language strings, never a numeric structure), letting the receiver corroborate a possibly-lying claim against real data via a new, more-trusted `BeliefMap.update_from_scent_report`. `rule-auditor` run against rules 23/26/27 and I6/I9 found zero fatal violations and one real non-fatal I9 gap — `_on_hint_received` was applying both belief updates before checking either field respected `hint_word_limit`, pre-existing since the original PRD 4 build, not a regression this revision introduced, but still live in the code this revision touched — gated each field independently on its own word count before it can touch belief state, fixed and re-verified. 212 tests (up from 197), 100% coverage
- [x] **Revision 1 hardening**: five targeted tests (outside-window no-signal, inside-window argmax quadrant, Intent never affects the scent portion, full field→language→belief round-trip within one cell, PRD 6 audit `xfail` guard) surfaced one more real gap — `dominant_scent_direction` was defaulting a genuinely all-zero window to a north-west guess instead of reporting no signal; fixed with a `None`/`"No scent detected."` sentinel path, gated on the receiving side so no belief update fires from it. New `RULE-19-SCENT-AUDIT-AT-PRD-6` marker (`tests/unit/test_prd6_scent_audit_guard.py`, `xfail(strict=True)`) documents that scent-report truthfulness is honest-by-construction only until PRD 6's commit-hash audit exists — same discipline as `RULE-27-REMOVE-AT-PRD-4`. 218 tests + 1 xfail (up from 212), 100% coverage
- [x] **Revision 2**: a cross-cutting critique pass found `dominant_scent_direction` computed a *relative* trail-lean excluding `own_pos`, while `interpret_hint` (reused for the scent report) decodes any direction words into a fixed *absolute* board quadrant — different claims, confirmed to actually break corroboration for an ordinary "moving into a corner" trajectory (ch. 4.4's own worked example reasons entirely over absolute cell coordinates, confirming absolute is the book-correct reading). Fixed per `TODO4-revision2.md`: `dominant_scent_direction` now sums every cell including `own_pos` into absolute quadrant buckets (new `board_size` parameter), matching `_quadrant`'s existing convention; `interpret_hint` needed no change. Milestone and unit tests rebuilt around a genuine SW-vs-NE counterexample, asserting the corroborated argmax lands in the *true* quadrant specifically, not merely that it beats the lie's. Sanity-checked by sabotage (reverting to the relative computation): the 4 rebuilt tests failed as expected while the original, weaker "beats the lie" assertion kept passing — proving the stronger assertion is what actually catches this. 249 tests + 3 xfailed, 100% coverage, `reasoning/hint.py` trimmed back under the 150-line cap after the fix (151 → 147)
- [x] **Revision 3**: `todoFullFix.md` §C — a further cross-cutting critique found Revision 1's entire natural-language `scent_report` mechanism was never book-mandated; ch. 6.4/6.5 describe a dedicated Tool-call data channel, separate from the verbal hint, not a second language field. Replaced: `receive_hint(text)` (narrowed, `scent_report` gone) + new `share_scent_map()` tool returning the sender's own `ScentField.full_field()` as structured numeric data (`{"cells": [[col,row,value],...]}`); `dominant_scent_direction`/`generate_scent_report`/`is_no_scent_report` deleted from `reasoning/hint.py`; `memory/belief.py` gains `update_from_scent_map` (real per-cell magnitudes, not a re-quantized focal point); `Orchestrator.request_scent_map_from_peer()` (new `orchestrator_peer.py` mixin) pulls the peer's map before computing the move. Rule 27 legal review submitted to `rule-auditor` as an explicit pre-commit gate (not a formality) — first pass found a real tension (the field's freshest value reveals the sender's near-exact current position every turn); raised to the project owner given the fatal-rule stakes, ruling: ship as built, the property is intrinsic to ch. 4.4's mechanic itself, not introduced by this redesign — see `FULLFIX.md`'s "Rule 27 legal review" for the full writeup. Found via reproduction while re-running the live demo script: a fixture coincidence (`previous_pos` landing exactly on the lie's decoded focal cell) let the lie win under the new numeric channel where the old language channel never surfaced it — fixed by choosing a fixture value clear of that coincidence. 266 tests + 3 xfailed, 100% coverage, `reasoning/hint.py` down to 82 lines after the deletions

**Demo script (run from repo root):**
```bash
uv run python scripts/watch_prd4_language.py   # local truthful/lying hints + belief shift, scent decay, one real round-trip with the actual wire text printed
```

## PRD 5 — Cloud exposure and tunneling — **BUILT, one step pending**

- [x] rule 10 — tunneling tool exposes the local server to the public internet (`tools/tunnel.py`, ngrok — real binary confirmed absent in this sandbox, so wiring/parsing is tested against a local admin-API stand-in; the tool itself is a real, non-fake subprocess wrapper)
- [x] hardening of rules 6/7 under real network conditions — no new production mechanism needed; new tests prove realistic non-zero latency doesn't falsely trip the deadline, and a connection that worked once then drops still reaches `TECHNICAL_LOSS` cleanly
- [x] build: ngrok integration (Localtonet deliberately not built — book permits either, building both is undocumented scope creep; documented choice, not a silent narrowing)
- [x] build: caller-IP capture (`X-Forwarded-For` preferred over the raw ASGI `request.client.host`, which is always `127.0.0.1` behind a tunnel) + `run_as_server`'s `use_tunnel`-gated `0.0.0.0` host binding (book's own ch. 2.3 FastMCP example binds this specifically "so a tunnel can expose it publicly")
- [x] test: a mid-game tunnel drop (connection worked once, then stops being reachable) produces a clean technical loss with an intact log — `tests/integration/test_tunnel_drop_mid_game.py`
- [x] found + fixed a real gap via sanity-check sabotage: uvicorn's own `ProxyHeadersMiddleware` (default-trusted for `127.0.0.1`) already rewrites `request.client.host` to match `X-Forwarded-For`, masking a real-HTTP test's ability to prove `_caller_ip()`'s own preference order — added an isolated test that monkeypatches the FastMCP dependency functions directly instead
- [x] `.claude/agents/adversary.md` written (hostile-peer simulator, read-only-verdict posture like `rule-auditor.md`) and run live once (via a general-purpose-agent stand-in — the registered subagent type isn't available until a fresh session): all three scenarios (drop mid-turn, delay past deadline, malformed payload) genuinely HELD against a real spawned peer process
- [ ] test: agent on a genuinely different network connects and plays a full round (milestone) — verify via connection-log IP, not localhost/LAN — **not yet run, needs a human with a real ngrok account and a second network**
- [ ] milestone watched end-to-end by a human — pending the above
- [x] `rule-auditor` run against rule 10, hardened 6/7, and I6/I9 — zero fatal violations; one non-fatal documentation-honesty finding (`TODO5.md` §7's checkboxes caught mid-edit by a race with the audit's own concurrent read) already fixed
- [x] `PRD/PRD-5-cloud-exposure.md` written; commit

**Demo script (run from repo root):**
```bash
uv run python scripts/watch_prd5_tunnel.py   # tunnel wrapper parsed against a local admin-API stand-in + caller-IP capture over real HTTP with a manually-set X-Forwarded-For header
```

## PRD 6 — Security and cryptography

- [x] rule 11 — config verified byte-for-byte identical with the opponent (`integrity/step0.py::verify_config_identity`, administrative per Design Question 3)
- [x] rule 17 — Commit-Reveal protocol based on SHA-256 (`integrity/commit_reveal.py`)
- [x] rule 18 — nonce kept secret until game end, generated via `secrets` (`integrity/nonce.py`; `_pending_nonces` retained, never sent by `commit_and_reveal_to_peer`) — secrecy verified clean; eventual disclosure via `receive_final_reveal` built and unit-tested but not yet called from the live turn loop (see PRD 6's "Known gap")
- [x] rule 19 — any hash mismatch at audit = technical forfeit (`integrity/audit.py::run_mutual_audit`, adversarially tested) — **self-audit half only**; the cross-peer half has no live wiring yet (PRD 6's "Known gap")
- [x] rule 21 — declare only the truth when a thief is captured (`integrity/capture_protocol.py::claim_capture`, pure function correct/tested) — not called from the live turn loop
- [x] rule 22 — never falsely declare a capture (`respond_to_capture_claim`, pure function correct/tested) — `receive_capture_response` (this repo's own receive side) unwired
- [x] rule 24 — Step-0 cryptographic hardware declaration before game start (`integrity/step0.py`/`hardware_declaration.py`) — signable and tested; exchanged out-of-band like config (Design Question 3), no wire tool, stated explicitly now
- [x] rule 53 — Step-0 records the exact commit hash being played (`current_git_commit_hash`)
- [x] enforcement half of rules 15/16 — barrier declaration truthfulness, checked at audit (`receive_barrier_declaration`, folded into that turn's commit) — send side live-wired and tested; receive side unwired (this repo is never the legitimate receiver)
- [x] build: `commit()`/`verify()` functions, canonical JSON (`sort_keys=True, separators`)
- [x] build: nonce generation via `secrets.token_hex`, never `random`
- [x] build: Step-0 declaration builder (hardware, LLM, token budget, commit hash)
- [x] build: `check_config.py --identical` wired into the pre-game gate
- [x] build: mutual end-of-game log audit — self-audit path; cross-peer path unwired
- [x] test: hash comparison uses `secrets.compare_digest` (also fixed in `step0.py::verify_config_identity`, found using `==` by `rule-auditor`)
- [x] test: nonce is not transmitted until the final reveal
- [x] test: a deliberately tampered log **fails** the audit (rejection test — `test_audit.py`'s adversarial milestone)
- [x] milestone watched end-to-end by a human — `scripts/watch_prd6_commit_reveal.py`: Step-0 signed, move committed/revealed, honest audit passes, tampered audit rejects
- [x] `rule-auditor` run, zero **fatal** violations — several non-fatal findings surfaced and are tracked (see PRD 6's "Known gap" section and retrospective item 5); two were fixed immediately (a nonce-key-type bug in `run_mutual_audit`, `verify_config_identity`'s `==`), the receiving-side wiring gap is documented as deferred, matching PRD 6's own out-of-scope boundary
- [x] `PRD/PRD-6-security-and-cryptography.md` written; commit

## PRD 7 — Reporting and visualization shell

Status: **Built & verified, with two acknowledged gaps** — full detail in `PRD/PRD-7-reporting-shell.md`'s own Retrospective. In short: every one of the six Build items exists, is tested, and (for the two with visible behaviour) was watched running live; the two gaps are (1) no automatic end-of-game sequence in `src/` chains the two audits + report bundle + Gmail send together yet, and (2) the capture-claim/response protocol (built in PRD 3/6, not this layer) is still unwired from the live turn loop. Neither is a PRD 7 checklist item that was skipped — both are new scope `rule-auditor`'s full-rule-set pass surfaced, deliberately left for a dedicated future PRD/TODO rather than absorbed silently into this closing pass.

- [x] rule 8 — live UI displays local truth only
- [x] rule 9 — live UI never displays the full objective board
- [x] rule 20 — Replay/verifier app built
- [x] rule 28 — token-bucket rate limiter for outgoing Gmail
- [x] rule 29 — DOS detector protecting network resources
- [x] rule 30 — Gmail API send-only scope
- [ ] rule 31 — minimum mandatory games played, against different teams (**[admin]** — needs real opposing teams; `league_ledger.py` tracks it)
- [ ] rule 32 — game results reported automatically via Gmail API (**gap** — `send_report`/`send_report_bundle` exist and are tested, but nothing calls them automatically at game end; see Retrospective)
- [x] rule 33 — report formatted as standard JSON
- [x] rule 34 — final report sent as JSON attachment, never free text
- [x] rule 35 — this side's own send is code; "opponent also reports and matches" is inherently cross-repo (**[honesty]**/**[admin]**)
- [ ] rule 36 — comprehensive mutual log audit at end of every game (**gap** — both audits are built and adversarially tested, but not chained into one automatic end-of-game call; see Retrospective)
- [x] rule 37 — `league_ledger.py` produces the count truthfully (**[honesty]** — nothing forces honesty, same as `Intent`)
- [x] rule 38 — same mechanism as 37, the lying-is-caught-at-reconciliation half
- [x] rule 39 — never push secrets/credentials, even to a private repo (swept, empty)
- [x] rule 40 — credentials/secrets added to `.gitignore`
- [ ] rule 41 — submission version tagged in git (**[admin]** — a command run once at submission time)
- [x] rule 42 — academic report written in `README.md` (created this closing pass; the six ch. 9.4.2 sections are present — screenshots still need a human with a display, see README's own `TODO:` marker)
- [ ] rule 43 — Moodle submission form downloaded, filled, saved as PDF unaltered (**[admin]**)
- [ ] rule 44 — submitted on Moodle separately by each team member (**[admin]**)
- [ ] rule 45 — unique 8-character team code, no spaces (**[admin]**)
- [ ] rule 49 — two separate GitHub repos, cross-linked in both READMEs (`README.md` has the section; the actual thief-repo URL is still a placeholder pending confirmation)
- [x] rule 50 — README/config/PRD/PLAN/TODO present in the repo (`README.md` was missing entirely until this closing pass — corrected)
- [x] rule 51 — reports sent to the lecturer's agent-reporting address (`config/game.toml`'s `[email].recipient`, read by `gmail_sender.py`)
- [x] rule 52 — exactly one counted game per opponent (`league_ledger.py` rejection-tested)
- [x] rule 54 — total tokens consumed reported in the final JSON
- [x] rule 55 — self-score covers code quality only, never the league result (**[admin]** — a framing instruction)
- [x] build: live GUI — belief heatmap + turn banner
- [x] build: Replay app — `Verified OK` / `TAMPERED` states
- [x] build: Gmail OAuth 2.0 setup (Appendix A), send-only scope
- [x] build: `ApiGatekeeper` — token bucket + DOS detector (reconciled with Table 19, see PLAN.md §4)
- [x] build: final JSON report generator
- [x] test: GUI cannot render the opponent's true position (check data reaching the render call)
- [x] test: Replay app rejects a tampered log, accepts a clean one (milestone)
- [x] test: report is an attached JSON file, never body text
- [x] test: `.gitignore` covers `credentials.json`/`token.json`/`.env`; `git log --all --full-history` finds no trace
- [x] research: results-analysis notebook + parameter-sensitivity pass + token-cost table (guide §9/§11)
- [x] milestone watched end-to-end by a human (`scripts/watch_prd7_live_gui.py`, `scripts/watch_prd7_replay.py`)
- [x] `rule-auditor` run — zero fatal-rule violations found live; two non-fatal wiring gaps documented (see Retrospective)
- [x] `PRD/PRD-7-reporting-shell.md` written; commit

## Cross-cutting / submission

- [ ] `README.md` written — install/usage, thief-repo link, screenshots (deferred from PRD 1's wrap-up, don't let it slip further)
- [ ] tag `v1.0-submission` pushed
- [ ] Moodle form filled, saved as PDF, fields untouched
- [ ] submitted on Moodle separately by each team member
- [ ] 8-character team code chosen and used consistently everywhere
- [ ] self-score write-up — code quality only
- [ ] warm-up games scheduled (uncounted, protocol shakeout)
- [ ] ≥2 counted games played against different teams
- [ ] config values agreed with the thief-repo partner before PRD 2 connects the two processes
