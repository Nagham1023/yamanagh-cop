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
- [ ] carried from PRD 1: enforce barrier "forgo move" once turn state exists (still deferred — turn state is PRD 3's territory)
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

## PRD 3 — Blind strategy

- [ ] rule 25 — move decision is never delegated to the LLM
- [ ] build: `BrainBase` extension contract (`_pick_move`, `_decide_move`)
- [ ] build: Manhattan-distance heuristic for the cop
- [ ] build: thief `_pick_move` — prefers cells with more escape routes
- [ ] build: cop `_decide_move` — barrier policy, never walls the cop off from the thief
- [ ] build: step-ceiling respected by both brains
- [ ] test: given a known target, shortest path computed and executed unattended (milestone)
- [ ] test: cop's barrier policy never traps the cop itself
- [ ] test: thief measurably prefers higher-escape-route cells
- [ ] milestone watched end-to-end by a human
- [ ] `rule-auditor` run, zero fatal violations
- [ ] `PRD/PRD-3-blind-strategy.md` written; commit

## PRD 4 — Language and scent

- [ ] rule 23 — scent-emission model cryptographically locked pre-game
- [ ] rule 26 — in-game communication is free natural language only
- [ ] rule 27 — no numeric position protocol (remove PRD 2's bare-coordinate scaffolding)
- [ ] build: Table 14 params (arena, hint word limit) wired from config
- [ ] build: scent emission + decay model per Table 16 constants
- [ ] build: Bayesian belief-map update from scent + hint
- [ ] build: LLM hint generation, `template` mode as zero-token default
- [ ] build: `Intent` truth/lie flag on outgoing hints
- [ ] build: hint word-limit enforcement in the LLM system prompt
- [ ] test: grep the wire — no coordinates survive anywhere in an outgoing hint
- [ ] test: belief map is a genuine probability distribution (sums to one)
- [ ] test: a known-false hint measurably shifts belief in the wrong direction (milestone)
- [ ] test: scent constants match Table 16 exactly, exposed for pre-game locking
- [ ] milestone watched end-to-end by a human
- [ ] `rule-auditor` run, zero fatal violations
- [ ] `PRD/PRD-4-language-and-scent.md` written; commit

## PRD 5 — Cloud exposure and tunneling

- [ ] rule 10 — tunneling tool exposes the local server to the public internet
- [ ] hardening of rules 6/7 under real network latency/loss
- [ ] build: ngrok/Localtonet integration
- [ ] build: reconnect/disconnect handling
- [ ] test: agent on a genuinely different network connects and plays a full round (milestone) — verify via connection-log IP, not localhost/LAN
- [ ] test: a mid-game tunnel drop produces a clean technical loss with an intact log
- [ ] milestone watched end-to-end by a human
- [ ] `rule-auditor` run, zero fatal violations
- [ ] `PRD/PRD-5-cloud-exposure.md` written; commit

## PRD 6 — Security and cryptography

- [ ] rule 11 — config verified byte-for-byte identical with the opponent
- [ ] rule 17 — Commit-Reveal protocol based on SHA-256
- [ ] rule 18 — nonce kept secret until game end, generated via `secrets`
- [ ] rule 19 — any hash mismatch at audit = technical forfeit
- [ ] rule 21 — declare only the truth when a thief is captured
- [ ] rule 22 — never falsely declare a capture
- [ ] rule 24 — Step-0 cryptographic hardware declaration before game start
- [ ] rule 53 — Step-0 records the exact commit hash being played
- [ ] enforcement half of rules 15/16 — barrier declaration truthfulness, checked at audit
- [ ] build: `commit()`/`verify()` functions, canonical JSON (`sort_keys=True, separators`)
- [ ] build: nonce generation via `secrets.token_hex`, never `random`
- [ ] build: Step-0 declaration builder (hardware, LLM, token budget, commit hash)
- [ ] build: `check_config.py --identical` wired into the pre-game gate
- [ ] build: mutual end-of-game log audit
- [ ] test: hash comparison uses `secrets.compare_digest`
- [ ] test: nonce is not transmitted until the final reveal
- [ ] test: a deliberately tampered log **fails** the audit (rejection test)
- [ ] milestone watched end-to-end by a human — move committed, revealed, Step-0 verified
- [ ] `rule-auditor` run, zero fatal violations
- [ ] `PRD/PRD-6-security-crypto.md` written; commit

## PRD 7 — Reporting and visualization shell

- [ ] rule 8 — live UI displays local truth only
- [ ] rule 9 — live UI never displays the full objective board
- [ ] rule 20 — Replay/verifier app built
- [ ] rule 28 — token-bucket rate limiter for outgoing Gmail
- [ ] rule 29 — DOS detector protecting network resources
- [ ] rule 30 — Gmail API send-only scope
- [ ] rule 31 — minimum mandatory games played, against different teams
- [ ] rule 32 — game results reported automatically via Gmail API
- [ ] rule 33 — report formatted as standard JSON
- [ ] rule 34 — final report sent as JSON attachment, never free text
- [ ] rule 35 — result agreed with opponent; each team sends its own separate report
- [ ] rule 36 — comprehensive mutual log audit at end of every game
- [ ] rule 37 — accurately declare games played so far, each game start
- [ ] rule 38 — never falsely declare games played
- [ ] rule 39 — never push secrets/credentials, even to a private repo
- [ ] rule 40 — credentials/secrets added to `.gitignore`
- [ ] rule 41 — submission version tagged in git
- [ ] rule 42 — academic report written in `README.md`
- [ ] rule 43 — Moodle submission form downloaded, filled, saved as PDF unaltered
- [ ] rule 44 — submitted on Moodle separately by each team member
- [ ] rule 45 — unique 8-character team code, no spaces
- [ ] rule 49 — two separate GitHub repos, cross-linked in both READMEs
- [ ] rule 50 — README/config/PRD/PLAN/TODO present in the repo (this file + `PRD/` in progress)
- [ ] rule 51 — reports sent to the lecturer's agent-reporting address
- [ ] rule 52 — exactly one counted game per opponent
- [ ] rule 54 — total tokens consumed reported in the final JSON
- [ ] rule 55 — self-score covers code quality only, never the league result
- [ ] build: live GUI — belief heatmap + turn banner
- [ ] build: Replay app — `Verified OK` / `TAMPERED` states
- [ ] build: Gmail OAuth 2.0 setup (Appendix A), send-only scope
- [ ] build: `ApiGatekeeper` — token bucket + DOS detector (reconciled with Table 19, see PLAN.md §4)
- [ ] build: final JSON report generator
- [ ] test: GUI cannot render the opponent's true position (check data reaching the render call)
- [ ] test: Replay app rejects a tampered log, accepts a clean one (milestone)
- [ ] test: report is an attached JSON file, never body text
- [ ] test: `.gitignore` covers `credentials.json`/`token.json`/`.env`; `git log --all --full-history` finds no trace
- [ ] research: results-analysis notebook + parameter-sensitivity pass + token-cost table (guide §9/§11)
- [ ] milestone watched end-to-end by a human
- [ ] `rule-auditor` run, zero fatal violations
- [ ] `PRD/PRD-7-reporting-shell.md` written; commit

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
