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
- [x] rule 49 — two separate GitHub repos, cross-linked (`README.md`'s own section, `config/game.toml`'s `[repos]` block: cop `https://github.com/Nagham1023/yamanagh-cop`, thief `https://github.com/yamandahle/thief-peer`) — this side's own two links confirmed; the thief repo's own README carrying the reverse cross-link is that team's job, not verifiable from here
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

## PRD 8 — Live match wiring

Status: **Built & verified.** Closes both gaps `rule-auditor`'s PRD 7 closing-pass review found: the capture-claim/response protocol (rules 21/22) is now called from the live turn loop, and an automatic end-of-game sequence (rules 32/36) runs the audits, league bookkeeping, and report send together for the first time. Full detail in `PRD/PRD-8-live-match-wiring.md`'s own Retrospective — including two real bugs found only by running the code (a cross-event-loop `asyncio.Event` thread-safety bug, and a pre-existing test that started hanging once real capture claims could fire), not anticipated by design review alone.

- [x] rule 1/2 — still no shared live state, no thief brain anywhere; every new test uses a second real cop `Orchestrator` standing in for the peer, same established discipline
- [x] rule 6/7 — the new capture-response wait reuses `AWAITING_REVEAL`'s already-legal `TECHNICAL_LOSS` edge (no new state-machine state); rejection-tested (a non-responding peer, and a peer lacking the tool entirely)
- [x] rule 19 — the audit half of end-of-game reporting now actually runs automatically (`report_game()`), not just on request
- [x] rule 21 — capture claims are now genuinely sent from live play (`play_game()` → `take_turn()` → `commit_and_reveal_to_peer` → `_claim_capture_if_warranted`), honestly grounded in the cop's own belief, not a verified fact (Design Question 1, confirmed against the book)
- [x] rule 22 — the response side is real and adversarially tested: a wrong belief gets `confirmed=False` and the game continues normally, not a technical loss
- [x] rule 31/37/38/52 — `league_ledger.record_counted_game` is now actually called at game end (`report_game()`, gated on a caller-supplied `is_counted`), not just built and unit-tested in isolation
- [x] rule 32/36 — the automatic end-of-game sequence: final reveal → self-audit → peer-audit → league record → report send through the Gatekeeper, in that order, tested directly
- [x] build: `reasoning/state.py::claims_capture()` — the honest, belief-only capture trigger
- [x] build: `orchestrator_capture.py` — capture-claim send-and-await, wired inside `commit_and_reveal_to_peer`'s own `AWAITING_REVEAL` window (not a new state)
- [x] build: `orchestrator_game_loop.py::play_game()` — the first live, multi-turn loop in this repo
- [x] build: `orchestrator_end_of_game.py::report_game()` — the automatic end-of-game sequence
- [x] test: the adversarial case — a claim built from a wrong belief is denied, not a rule 21 violation and not a technical loss (Design Question 1's own milestone)
- [x] test: a peer that never responds to a claim, and a peer lacking the tool entirely, both reach `TECHNICAL_LOSS` within the deadline
- [x] test: `play_game()` genuinely stops the instant an `Outcome` is reached — no extra turn
- [x] test: `report_game()` calls each step in the documented order, and respects `is_counted`
- [x] milestone watched end-to-end by a human (`scripts/watch_prd8_live_match.py`) — a real confirmed capture ending a match in one turn, and a denied claim continuing to an ordinary `SURVIVAL` ending, both live
- [x] `rule-auditor` run — see `PRD-8-live-match-wiring.md`'s own Retrospective for the full findings
- [x] `PRD/PRD-8-live-match-wiring.md` written, critiqued, corrected, and built; `TODO8.md` executed in full; commit

## PRD 9 — Step-0 negotiation ceremony

Status: **Built & verified.** Closes all four gaps `cop-team-fix-list.md` (the Thief side's review) flagged: rule 23 **[FATAL]** had no scent-model cryptographic lock; rule 11 **[FATAL]**'s `verify_config_identity()` was built but never called from anywhere; rule 49 had no channel for the opponent's own repo URLs; and there was no live Step-0/negotiate exchange tool at all. All four shared one root cause — `Step0Declaration` existed and was unit-tested in isolation but never put on the wire — same shape of gap PRD 8 closed for capture-claim/end-of-game. Full detail in `PRD/PRD-9-step0-negotiation.md`.

- [x] rule 9 — both the initiator (`negotiate_step0`) and the responder (`_on_step0_received`) independently verify the peer's declaration; a malformed shape, a forged signature, or a hash mismatch is rejected on whichever side detects it, not trusted from either direction
- [x] rule 11 — `config_sha256` is now compared live, automatically, before any turn is played (`_verify_peer_step0`), not only by a human running `check_config.py --identical` on demand
- [x] rule 23 — `scent_model_sha256` (`integrity/scent_model_lock.py`), a hash of the fixed formula shape + this series' numbers + a worked numeric example, exchanged and verified before move 1
- [x] rule 24 — `Step0Declaration` (hardware, code commit hash, group name, sub-game number) now genuinely exchanged over MCP, not just constructed and left local
- [x] rule 49 — `repos` rides alongside the signed declaration in `receive_step0`; `report_game()` sources `opponent_cop_repo_url`/`opponent_thief_repo_url` from a completed negotiation by default, explicit override still supported
- [x] build: `integrity/scent_model_lock.py::compute_scent_model_hash()` — computed via a real `ScentField.advance()` run, not hand-typed
- [x] build: `integrity/step0_wire.py` — wire (de)serialization, split out once `orchestrator_step0.py` hit the 150-line cap
- [x] build: `tools/mcp_server_prd9.py`/`mcp_client_prd9.py::receive_step0`/`send_step0` — one synchronous round trip
- [x] build: `orchestrator_step0.py::Step0NegotiationMixin` — `negotiate_step0`/`_on_step0_received`, both running the identical `_verify_peer_step0` check
- [x] build: `planner/state_machine.py` gains `NEGOTIATING` as a legal (not default) state
- [x] test: two real `Orchestrator`s — a genuine match succeeds; a mismatched `config_sha256`, a mismatched `scent_model_sha256`, and a forged signature are each rejected independently (three separate rejection tests, house rule)
- [x] test: `report_game()` sources opponent repo URLs from a completed negotiation, an explicit override still wins, and it raises clearly when neither is available
- [x] milestone watched end-to-end by a human (`scripts/watch_prd9_step0_negotiation.py`) — a genuine mutual lock, and a clean, mutually-visible `TECHNICAL_LOSS` on a real single-byte config mismatch, both live
- [x] found and fixed in passing: `test_private_config.py` asserted a stale placeholder repo URL left over from before the real URL was confirmed (`f6397bf`) — confirmed pre-existing via `git stash`, not a regression, fixed as a one-line drift correction
- [x] `PRD/PRD-9-step0-negotiation.md` written and built; `TODO9.md` executed in full; `WIRE-CONTRACT.md`'s ch. 4.5 section updated from "still not built" to describe the shipped ceremony; commit

## PRD 10 — CLI entry point, complete report bundle, and online-match readiness

Status: **Built & verified.** Closes both polish gaps named directly: no `src/cop/__main__.py` existed despite `CLAUDE.md`/`README.md` documenting `uv run python -m cop peer`/`replay --log <path>` (PRD 7's own "Explicitly out of scope" section named this and deferred it); `report_game()` attached only `result_<game_id>.json`, not all four Table 20 files. Designing the CLI surfaced a third gap neither item named — nonces lived only in live process memory, so a standalone `replay --log <path>` run against a completed match's log file had no way to cryptographically verify it — fixed in the same pass since it blocked the `replay` subcommand from working as documented. Full detail in `PRD/PRD-10-cli-and-online-readiness.md`.

- [x] rule 18/20 — `send_final_reveal_to_peer` now logs the revealed nonces themselves (not just a count), unconditionally, before attempting the send — `nonces_from_log` (new) is the CLI `replay` subcommand's only source for them, since the live process that played the match has usually already exited
- [x] rule 20 — `uv run python -m cop replay --log <path>` is a real, headless-by-default verifier: `Verified OK`/`TAMPERED`/a clear error on an incomplete log, each a distinct process exit code
- [x] rule 34/49 — `report_game()` attaches all four Table 20 files (`declaration_`, `config_`, `log_`, `result_`) in one email, each round-tripping cleanly through JSON
- [x] rule 6/7 — the CLI's passive Step-0 wait (`await_passive_step0`) reuses PRD 8's own cross-thread `Event`/`call_soon_threadsafe` pattern; a genuine timeout reaches `TECHNICAL_LOSS` cleanly, not a hang — and (`rule-auditor`'s own reproduced finding) a negotiation that already completed *before* the wait was even called is recognized via `self._step0_completed`, not silently discarded and re-waited on for the full timeout
- [x] build: `cli_peer.py::run_peer` / `cli_replay.py::run_replay` / `__main__.py` — the CLI itself; confirmed both sides always drive their own turns regardless of who negotiates first (`orchestrator_turn.py::take_turn` read directly before designing this)
- [x] build: `orchestrator_step0_wait.py::Step0PassiveWaitMixin` — `await_passive_step0`, the CLI's non-initiating side
- [x] build: `orchestrator_game_loop.py` stamps `_match_started_at`/`_match_ended_at`; `report_bundle.py::load_config_dict`/`load_log_entries` — the two Table 20 files that had loaders but no reader before this
- [x] build: `scripts/setup_gmail_oauth.py` — the one-time OAuth consent flow `gmail_sender.py`'s own docstring referenced but never built
- [x] test: two real, independent `run_peer()` calls (initiator + passive) reach a genuinely negotiated, played, and reported match through the CLI itself, not a hand-assembled `Orchestrator`; `--counted` verified to actually reach the league ledger
- [x] test: `run_replay` — verified-ok/tampered/incomplete-log, each a distinct rejection case (house rule)
- [x] found and fixed in passing: `report_bundle.py`'s own docstring claimed `token_budget_per_series` wasn't tracked — it already was, on `GameConfig`; same stale-claim drift PRD 9 found and fixed for `verify_config_identity`
- [x] found only by running `uv run python -m cop peer` as two real subprocesses, not by any unit test: `config_filename`/`log_filename` were called with an already-suffixed `game_id` instead of the bare `group_id`, doubling `_g01` in real filenames on disk — the one test checking this mirrored the same bug in its own expected values, so the suite stayed green; fixed in both call sites and that test, re-verified with the same literal CLI run
- [x] `rule-auditor` run scoped to rules 6/7/18/20/34/49 — found two further real gaps the run above didn't: `declaration_filename`/`result_filename` still received the already-suffixed `game_id` too (Table 20's own `PARAMETERS.md` text specifies bare `game_id` for both, no per-sub-game suffix at all), and a genuine, empirically-reproduced race in `await_passive_step0` that could discard an already-successful negotiation and burn the full timeout on a spurious `TECHNICAL_LOSS`; both fixed with regression tests before this line was written (`PRD-10-cli-and-online-readiness.md`'s own Retrospective has the full account, including why two different verification techniques — running the CLI, and the scoped audit — each caught what the other missed)
- [x] `instructions.md` written (full submission-readiness scope, confirmed with user) — ngrok, Gmail OAuth, real config exchange, running matches, the three still-open screenshots, the rules 41-45 submission checklist
- [x] `PRD/PRD-10-cli-and-online-readiness.md` written and built; `TODO10.md` executed in full; commit

## PRD 11 — RL training simulator and tabular Q-learning brain

Status: **Built & verified.** The RL layer `PRD-3-blind-strategy.md` deferred ("treat it as optional, later-if-time"), picked up now as the first of a three-layer plan (11: this layer; 12: quantization, not yet built; 13: pipeline orchestration and gated deployment, not yet built). Nothing from this layer is wired into any real match — `RLCopBrain` is fully built and tested but not yet referenced from `cli_peer.py` or `config/game.toml`. Full detail in `PRD/PRD-11-rl-training-simulator.md`.

- [x] rule 25/I7 — `RLCopBrain._pick_move` always intersects the Q-table's ranked actions with a Python-computed legal set; a table miss or missing checkpoint falls back to the inherited `CopBrain` heuristic, never a guess
- [x] rules 1/2 — `training/` is a new top-level, sandbox-only package with a one-directional dependency on `src/cop/`, enforced by `tests/unit/test_training_boundary.py`; synthetic sparring opponents are plain functions, never a `BrainBase`/`ThiefBrain` subclass
- [x] I6 — every game magnitude the encoding touches is read from the `Board`/`BarrierSet`/`GameConfig` objects already in scope; RL hyperparameters live in `config/rl_training.toml`, explicitly outside Appendix F and `check_config.py`'s scope
- [x] build: `src/cop/reasoning/rl_state_encoding.py`, `rl_checkpoint.py`, `rl_cop_brain.py` — the production-side files
- [x] build: `training/` — `config.py`, `opponent_policies.py`, `reward.py`, `q_table.py`, `env.py`, `train_loop.py`, `checkpoint_io.py`
- [x] found only by running the parity test, not by inspection: `SelfPlayEnv`'s first draft double-checked capture (once after the cop's move, once after the thief's) — physics-wrong, since the thief walking onto the cop is never itself a capture; fixed to check exactly once, matching `run_local_subgame`'s own order
- [x] test: 50 new tests, 100% coverage on every new module; full existing `tests/unit/` suite re-run in batches with zero regressions (three pre-existing, environment-specific real-HTTP-server hangs confirmed identical on a clean `main` via `git stash`, not introduced here)
- [x] milestone watched: `scripts/watch_prd11_rl_training.py` — 2000 episodes trained in 0.50s, reward climbed from 13.83 to 20.44 average, `RLCopBrain` reached a 100% capture rate vs. a random baseline's 10% over 20 seeded episodes
- [x] `rule-auditor` run scoped to rules 1/2/25/I2/I6/I7 and the new files
- [x] `PRD/PRD-11-rl-training-simulator.md` written and built; `TODO11.md` executed in full; commit

## PRD 12 — Quantization, latency benchmark, and promotion-gate criteria

Status: **Built & verified.** Extends PRD 11's checkpoint format (backward compatible — a PRD-11-era checkpoint still loads unchanged) rather than replacing it. Nothing from this layer is wired into any real match either; still off the graded critical path. Full detail in `PRD/PRD-12-quantization-and-benchmarking.md`.

- [x] design — per-table affine int8 quantization of a Q-table's stored values, the tabular analogue of PyTorch's post-training weight quantization; stated up front that lookup latency's benefit isn't load-bearing for a tabular table (confirmed by the measured numbers, not assumed)
- [x] build: `src/cop/reasoning/rl_checkpoint_quant.py` — `QuantizationParams`, `dequantize_q_table` (the one authoritative decode implementation)
- [x] build: `rl_checkpoint.py` extended with an optional `quantization` field — transparent dequantize on load, backward compatible with PRD 11's own unquantized format
- [x] build: `training/quantize.py` — `quantize_q_table`, `argmax_agreement_rate`; `training/benchmark_latency.py` — realistic-state sampling + p50/p95/p99 timing; `training/checkpoint_io.py` gains `save_quantized()`
- [x] found only by deliberately constructing an adversarial near-tie case, not assumed: the argmax-agreement metric is proven to actually detect a real divergence (0.5, not 1.0, on a table engineered to collapse a genuine tiny margin into a quantized tie)
- [x] test: 22 new tests, 100% coverage on every new/extended module; full PRD-11+12 suite together, 65 passed
- [x] milestone watched: `scripts/watch_prd12_quantization.py` — 41% size reduction, 90.84% argmax-agreement (a real, honestly-reported number — not assumed to be 100%), p99 latency ~752,000x under the 30s `response_timeout_seconds` budget
- [x] `rule-auditor` run
- [x] `PRD/PRD-12-quantization-and-benchmarking.md` written and built; `TODO12.md` executed in full; commit

## PRD 13 — ML pipeline orchestration and human-gated deployment

Status: **Built & verified through the gate; promotion commit intentionally not made.** Closes the loop on PRD 11/12: a real end-to-end pipeline run, a real scoped `rule-auditor` pass, and a real `ml-promotion-gate` `PASS` verdict all exist for a genuine candidate checkpoint — but creating `training/promoted/` and making the commit that would ever change `RLCopBrain` from an override into the default is left for a human, per `PLAN.md` §8's own checkpoint table. Full detail in `PRD/PRD-13-ml-pipeline-and-deployment.md`.

- [x] rule 25/I7, I2, I6 — see `PRD-13-ml-pipeline-and-deployment.md`'s own rules-owned table
- [x] build: `src/cop/shared/strategy_loader.py` (dynamic `police_class` loader), `src/cop/shared/promotion_guard.py` (hard runtime guard for counted games), `src/cop/cli_peer_build.py` (split from `cli_peer.py` for the 150-line cap)
- [x] build: `training/pipeline/{artifacts,stages,refinement_loop}.py` — the pipeline's substantial, testable logic; `scripts/ml/orchestrate_pipeline.py` — the thin CLI wrapper
- [x] build: `.claude/agents/{ml-training-runner,ml-experiment-reporter,ml-promotion-gate}.md`, `.claude/skills/ml-pipeline-guard/SKILL.md` — all exercised for real this session, not just written
- [x] found only by running it: `artifacts.py`'s `checkpoint_path` didn't ensure the run directory existed (fixed); `run_train_eval_cycle` didn't persist its own result for a cold reader (fixed, see PRD's Design Question 2)
- [x] found only by running the real two-process milestone: a pre-existing, unrelated mutual-Capture-Claim `TECHNICAL_LOSS` bug (PRD 6/8 territory) — reproduced, root-caused, routed around, recorded as a known issue below, not fixed here
- [x] test: 33 new tests, ~99% coverage; zero regressions on `cli_peer`-adjacent tests
- [x] real run: `--stage refine` converged round 1 (win_rate=1.0 vs. target 0.6); quantize/benchmark on the winner (91.22% argmax-agreement, p99 latency millions-of-times under budget); scoped `rule-auditor` CLEAN; `ml-promotion-gate` verdict **PASS** (with an honest thin-eval-sample caveat, not smoothed over)
- [x] milestone watched, repeatable: two real `run_peer()` processes, one running `RLCopBrain` via `police_class`, both reach a completed, reported match
- [x] `PRD/PRD-13-ml-pipeline-and-deployment.md` written and built; `TODO13.md` executed in full; commit — training/promoted/ and the promotion commit itself deliberately not included

## PRD 14 — Belief-aware state, barrier-placement RL, and pipeline provenance

Status: **In progress.** Refines and extends PRD 11-13 per a user-supplied optimization proposal, itself refined against the book/architecture before building (co-evolution and Orchestrator wiring explicitly excluded; belief-confidence seam stays inert; "automate rule-25 into evaluate" explicitly rejected, documented-only). Approved plan: `/home/nagham1023/.claude/plans/sprightly-spinning-fog.md`. Nothing from this layer is wired into any real match either.

- [x] provenance — `training/pipeline/artifacts.py::write_provenance` records `git_commit_hash`, `hardware`, the real `RLTrainingConfig`, and the game config's own SHA-256 with every training run; wired into `run_train`/`run_train_eval_cycle`
- [x] sub-layer A — belief-based state encoding: `State` grew a confidence bucket; `SelfPlayEnv` now advances a real `BeliefTracker` (scent field + belief map, the same two objects a live turn updates) and encodes its *estimate*, never ground truth, closing a real train/inference mismatch nobody had tested before (`RLCopBrain` always received the belief map's guess at real-match time, but training saw perfect information); `RLCopBrain` gained an optional `belief_confidence_provider` seam, deliberately left unbound (confirmed decision); new additive `run_evaluate_belief_aware` stage, real result: RL policy beat a naive heuristic under genuine uncertainty (0.35 vs. 0.0 capture rate) even though its ground-truth win-rate dipped slightly (1.0 -> 0.85, an honest, reported side effect of confidence defaulting to 1.0)
- [x] reward-shaping docs — `training/reward.py`'s docstring now derives the exact Ng/Harada/Russell (1999) potential-based-shaping identity and states plainly that this repo's implementation omits the `γ` multiplier on `Φ(s')` (a documented approximation, not a hidden bug); turned into a checked regression test, not just prose
- [x] third curriculum stage — `lookahead_evader_thief` (depth-2 own-mobility lookahead, never sees the cop's position — the `ThiefMover` interface structurally can't supply it, verified genuinely different from the 1-ply heuristic via a 20,000-trial search, not just documentation-different); `curriculum_switch_episode_2` added to config/toml/train_loop
- [x] sub-layer B — barrier-placement RL: `State` grew barrier-count and enclosure buckets (both quota-relative, I6); `SelfPlayEnv` now simulates real `BARRIER_<dir>` actions through the real `BarrierSet`; `RLCopBrain._decide_move` overridden for the first time — Q-table drives the barrier-vs-move choice, every ranked action re-checked live before use (rule 25/I7), falling back to `CopBrain`'s full heuristic on a genuine table miss; checkpoint version bumped to `"v3"` (a real `"v1"` *and* `"v2"` file both now fail closed, verified against real file shapes, not re-asserted)
  - [x] **found only by running it, not by inspection**: `training/env_actions.py`'s movement-legality check only ever verified board bounds (`apply_move` alone) — it never checked `barriers.blocks(...)`, unlike every real caller (`CopBrain._pick_move`). Before this fix, a cop could "move" onto its own placed barrier, and `legal_actions()` offered barrier-blocked directions as ordinary legal moves. Fixed in both `legal_cop_actions` and `apply_cop_action`.
  - [x] **found only by running a real 2000-episode training run against the real production config, not by inspection**: with barriers enabled, trained-policy reward genuinely *degraded* with more training (first-half avg 10.62 -> last-half avg 7.09) instead of improving — a serious correctness problem, since it meant the resulting Q-table would be actively worse than no training at all. Root-caused by rolling out the fully-greedy trained policy and watching it happen: the cop placed barriers early and sometimes walled off its own last remaining exit, then spent the rest of the episode STAY-looping to a `SURVIVAL` timeout instead of ever reaching the thief again — a self-entrapment failure mode `CopBrain`'s own heuristic avoids by construction (`_barrier_candidates` excludes its own preferred next step) but that nothing in the learned Q-table process shared. **Fix**: `legal_cop_actions` now excludes any barrier candidate that would seal the cop's own *last* open move — evaluated fresh against the live board every call, so it structurally can never allow the actual final sealing placement regardless of how many turns of accumulated barriers led up to it. Re-verified on the same real config after the fix: first-half avg 11.05 -> last-half avg 13.04, reward climbing again.
  - [x] **found only by running the existing regression test against the new, much larger state/action space**: `test_average_reward_in_the_second_half_beats_the_first_half`'s original 400-episode/2-stage-split design (pre-dating both sub-layers) no longer converges reliably — states_visited grew ~3-9x (barrier-count/enclosure buckets, up to 9 actions per state at the real quota=14) and, separately, the second-half window now systematically faces a *harder* opponent once a third curriculum stage exists, confounding "did it learn" with "did the opponent get harder" (a second, distinct instance of the curriculum-ordering trap PRD 14 already found once). **Fix**: episode_count raised to 2000, curriculum pinned to a single stage for the test's own run (isolating the learning signal), and the comparison changed from first/second-half to first/last-10% (verified reliable across 8 seeds; halves stayed marginal or flipped for 2-3 of the same seeds even at 2500 episodes)
  - [x] test: `test_env_actions.py` (new, 6 tests), `test_env.py` (+4: quota exhaustion, over-quota no-op, both movement-legality-bug regressions), `test_rl_cop_brain.py` (+5: barrier-adjacent-visited-vs-unvisited, ranked-barrier-becomes-PlaceBarrier, illegal-ranked-barrier-skipped, full `_decide_move` legality sweep), `test_rl_checkpoint.py` (+1: a real "v2" file now fails closed too), `test_training_env_parity.py` (+1: `SelfPlayEnv` vs. `run_local_subgame` with the real barrier_quota=14, covering all three capture shapes — coordinate, barrier/rule-46, imprisonment/rule-47 — the last only reachable in `SelfPlayEnv` for the first time)
  - [x] real run against the actual production config (2000 episodes): states_visited=2424, reward tail healthy; `--stage all` end-to-end clean — evaluate 0.75 win-rate vs. baseline (ground truth), 0.25 win-rate belief-aware (RL beats baseline's 0.0 belief-aware capture rate); quantize argmax-agreement 89.36% (expected to need task below); benchmark margin ~1.36M x under budget
- [x] per-row quantization — `PerRowQuantizationParams`/`dequantize_q_table_per_row` (`rl_checkpoint_quant.py`), `quantize_q_table_per_row` (`training/quantize.py`), a `"mode"` key inside `"quantization"` (`"per_row"`/`"per_table"`, defaulting to `"per_table"` when absent — verified against a real hand-constructed pre-existing-shape file, exact backward compat); `checkpoint_io.save_quantized`/`pipeline/stages.py::run_quantize` both switched to per-row. Real result: argmax-agreement 89.36% -> **100%** on the same real full-config checkpoint (up from PRD 12's own 90.84%/91.22%, the exact "still too low" trigger this task existed to answer)
  - [x] **found only by running it, not by inspection**: the first working version made the checkpoint *larger* than the unquantized original (328KB vs. 218KB, +50%) — a separate `"rows"` list re-serialized every state's key a second time, and Python's default float repr carried ~17 significant digits nothing here needs. **Fix**: per-row `(scale, min_q)` now lives inline in each `q_values` entry instead of a separate list (`rl_checkpoint_json.py`, split out of `rl_checkpoint_quant.py` for the 150-line cap once this landed), rounded to 10 decimal places (far finer than int8's own ~1/255 resolution — verified `argmax_agreement_rate` unchanged before vs. after rounding). Brought it down to 230KB (+5% over unquantized) — a real, honestly-reported, now-small trade-off for 100% decision fidelity, not eliminated entirely: a row with only one action can't amortize the fixed per-row overhead at all (verified both ways — a realistic 5-actions/row table IS smaller than float; a 1-action/row table can legitimately be ~1.2x larger, a real structural property of the technique, not a bug)
  - [x] updated 3 tests whose "quantized must be smaller" assumption predated per-row mode and is no longer universally true (`test_pipeline_stages.py`, `test_checkpoint_io.py` x2) — each now either confirms the realistic case still saves space, or bounds against a *runaway* size blow-up (the specific bug shape found above) rather than asserting an unconditional "smaller"
  - [x] test: `test_quantize.py` (+4: per-row round-trip, rows recover independently not against a shared table scale, the cross-row-contamination case PRD 12's own adversarial test exposed is now fully resolved, a genuine within-row divergence is still caught — proving the metric isn't vacuously 1.0 for per-row either), `test_rl_checkpoint_quant.py` (+2: per-row dequantize, `dequantize_any` dispatch), `test_rl_checkpoint.py` (+2: a real pre-per-row-mode file — `"quantization"` with no `"mode"` key at all — still loads as per-table; a per-row-quantized checkpoint round-trips through the real `save_checkpoint`/`load_checkpoint` pair)
  - [x] real run against the actual production config (2000 episodes, full pipeline `--stage all`): argmax_agreement_rate=1.0, size_reduction_fraction=-0.054 (honestly negative, not smoothed over), benchmark margin ~1.79M x under budget
- [x] full pipeline re-run + PRD write-up — pipeline itself re-verified end-to-end multiple times across this layer's tasks (see each task's own "real run" line above); the PRD document write-up remains open
- [x] `training/q_table.py`'s unused `_ACTIONS` constant deleted rather than "updated" — grep-confirmed it was never referenced anywhere (`train_loop.py` gets its action list from `env.legal_actions()` instead); house rule favors deleting confirmed-dead code over patching a constant nothing reads
- [x] **Follow-up, post-gate**: `ml-promotion-gate`'s own thin-sample caveat (20 episodes) addressed directly — `_EVAL_EPISODES` raised to 200 in `training/pipeline/evaluate_stages.py` (`run_evaluate`/`run_evaluate_belief_aware` both share the one constant). Re-run against the real gate candidate confirms the finding is robust, not an n=20 fluke: ground truth 0.75->**0.83** (166/200 vs. baseline's 200/200), belief-aware 0.25->**0.24** (48/200 vs. baseline's 0/200) — essentially unchanged. The core tension the gate surfaced (worse than baseline under ground truth, better under belief-aware ambiguity) holds at 10x the sample size.
- [x] **Follow-up, post-gate — `HybridCopBrain`**: new `src/cop/reasoning/hybrid_cop_brain.py`, a confidence-gated router (`CopBrain` when the belief map is genuinely confident, `RLCopBrain` when it isn't) responding directly to the gate's own tension — built and fully tested (9 tests, including a property-based legality sweep across all four confidence buckets) but **left completely unwired**, same "built, tested, inert" posture `RLCopBrain` has held since PRD 11. Reuses the *existing* `_CONFIDENCE_THRESHOLDS`/`_bucket_confidence` machinery for the switch point (bucket 3, `>=0.6`) rather than a new standalone magic number — comparing via the real function means the router structurally can't drift from the Q-table's own bucketing.
- [x] **Follow-up, post-gate — chokepoint measurement**: new `training/pipeline/barrier_restriction_metric.py` (+ `scripts/measure_barrier_restriction.py`) measures, against a real trained checkpoint, whether the Q-table's own top-ranked barrier choices restrict the *believed* target's escape routes — built specifically to decide whether a new, not-provably-safe reward-shaping term was worth the risk, rather than building it on spec. Real measurement against `prd14_gate_candidate_round1`: **14.8%** (61/412 barrier-top-ranked states) — comfortably below the plan's own ~0.5 threshold, confirming the gap was real, not assumed.
- [x] **Follow-up, post-gate — belief-aware barrier reward shaping, with a real regression found and fixed before shipping**: `training/reward.py::step_reward` gained `restricts_believed_target` (new `barrier_restriction_bonus_weight` config field, `env.py::step`/`env_actions.py::barrier_restricts_believed_target` compute it from the belief target captured *before* the action mutates anything — a real ordering trap found during design, not the code). **First real run at the initially-chosen weight (0.5) was a genuine regression**: belief-aware win-rate collapsed from 0.24 to **0.00** on the same checkpoint — the exact failure mode the term's own honesty caveat predicted ("could bias toward premature/wasteful barrier placements"), now confirmed empirically rather than left hypothetical. **Root-caused via a weight sweep** (0.05/0.1/0.2/0.5 on a single seed — noisy, non-monotonic, 0.1 alone looked good) **then a properly controlled 5-seed comparison** (same 5 seeds, only `weight` differing): `weight=0.1` roughly doubles the 5-seed-average belief-aware win-rate (0.112 -> 0.272) with no ground-truth cost, though individual seeds still range 0.00-0.48 — real variance a tabular setup this small doesn't fully average out, stated honestly rather than smoothed over. **Shipped default: `0.1`**, not the originally-guessed 0.5 — the sweep, not intuition, picked the number. All sweep/verification run directories cleaned up (gitignored `training/runs/`, nothing to commit there).

## Cross-cutting / submission

- [x] `README.md` written — "Running it" (install/usage), thief-repo link (confirmed: `https://github.com/yamandahle/thief-peer`) — [ ] screenshots (`screenshots/live_gui_verified.png`, `replay_verified_ok.png`, `replay_tampered.png`) still need a human with a display to run `scripts/watch_prd7_live_gui.py`/`watch_prd7_replay.py` and capture them (`instructions.md` §7 has the exact steps)
- [ ] tag `v1.0-submission` pushed (`instructions.md` §9)
- [ ] Moodle form filled, saved as PDF, fields untouched (`instructions.md` §9)
- [ ] submitted on Moodle separately by each team member (`instructions.md` §9)
- [ ] 8-character team code chosen and used consistently everywhere (`instructions.md` §9)
- [ ] self-score write-up — code quality only (`instructions.md` §9)
- [ ] warm-up games scheduled (uncounted, protocol shakeout) (`instructions.md` §6)
- [ ] ≥2 counted games played against different teams (`instructions.md` §6)
- [ ] config values agreed with the thief-repo partner (`instructions.md` §2 — now includes `WIRE-CONTRACT.md` exchange and `initiate_step0` assignment, not just the shared config file)
- [ ] Gmail OAuth `token.json` obtained, ngrok authtoken configured (`instructions.md` §3-4) — needed before `email.mode = "send"` or `--tunnel` work for real
- [x] **Fixed**: `tests/unit/test_cli_peer.py::test_run_peer_two_real_processes_reach_a_completed_and_reported_match` was a real, uncaught red test at HEAD (`uv run pytest` was not actually clean) — a fresh full-repo `rule-auditor` sweep reproduced it deterministically. Root cause: two real `run_peer()` processes here are both cop-role (rule 1/2 — this repo can never run a thief brain), and `PlaceBarrier` claims unconditionally (rule 46, matching belief not required), so both sides' very first-turn barrier placement fired a mutual Capture Claim that neither side could legitimately answer — per the book (ch. 3.4), **only the cop ever sends a Capture Claim, and only the thief is ever obligated to answer one**; this repo's own self-play tests have no thief on either end, so the collision is a test artifact, not a real-match scenario. **First attempt was wrong and reverted**: initially wired the cop's own `_on_capture_claim_received` to answer received claims honestly using its own position — technically didn't share thief state (rule 1/2 held), but gave the cop a capability the book reserves for the thief role only, and `CaptureResponse` always carries `true_thief_pos` *unconditionally* (confirmed or not) — that would have let any peer, including a misbehaving one, get this side's exact position just by sending it a bogus claim, undermining the fog-of-war the whole project is built on. Reverted before landing. **Actual fix**: `tests/unit/test_cli_peer.py::_fast_shared_config` now also sets `max_barriers=0`, the same technique `scripts/watch_prd13_rl_deployment.py` already uses to route around this same protocol shape — sidesteps a scenario the protocol was never meant to face instead of adding cop-side capability that shouldn't exist. Zero production code changed; verified deterministic across 5 repeated runs.
  - [x] **Fixed**: the *different*, also pre-existing bug found while investigating the above — 5 of `tests/unit/test_orchestrator_take_turn.py`'s 12 tests (any that trigger a capture claim through `take_turn()`, either from a fresh belief map's `most_likely_cell()` tying to `cop_start`, or `_AlwaysPlacesABarrierOnItsOwnCell`'s unconditional barrier claim) hung 30s and failed — its own `_start_server()` peer never had anywhere to route an answer, real or not. Confirmed pre-existing via `git stash` against clean HEAD. **Fix, same "test the test, not the cop" lens as the entry above**: production code stays untouched (`git status src/` clean) — added a test-only honest capture-claim responder (`_make_capture_responder`), patched onto the `Orchestrator` *class* only for the duration of constructing the one instance standing in as the peer (a bound method captured inside `__init__` is fixed at construction time — patching the instance afterward has no effect, learned by trying it first and watching it silently do nothing). First attempt used an `async def` responder and silently failed for a second, more basic reason: `receive_capture_claim` calls its callback *synchronously* and discards the return value, so an `async def` callback just created an unawaited, never-run coroutine — fixed by using the same sync-callback-spawns-a-thread shape `test_orchestrator_capture.py`'s own `_start_thief_peer` already established for the identical reason. All 12 tests pass, verified deterministic across repeated full-file runs, `ruff` clean.
