# CLAUDE.md

Project context, loaded automatically every session. Read `PLAN.md` before doing structural work.

## What this repo is

One peer of a two-peer, judge-free pursuit game. **This repo contains exactly one role** — cop *or* thief, never both. The other role lives in a separate repo and runs as a separate OS process. Final project for *Orchestration of AI Agents*, University of Haifa; spec is book v3.0.0 by Dr. Yoram Segal.

Two agents (n = 2) play across the public internet over MCP. Neither sees the true board. Each infers the opponent's position from a decaying scent field plus a natural-language hint the sender may falsify. There is no referee — integrity comes from SHA-256 Commit-Reveal plus a mutual log audit.

## Non-negotiable invariants

Check these before writing any code. Full detail in `PLAN.md` §3.

1. **One role per repo, one role per process.** Never instantiate both brains in one interpreter outside pure board-logic unit tests. No shared live state, ever.
2. **All subsystem access goes through the Orchestrator.** Nothing reaches `domain/` directly.
3. **An explicit state machine governs progress**, and rejects illegal transitions rather than absorbing them.
4. **Every wait on the opponent has a deadline.** A watchdog supervises the process and extracts data on crash.
5. **The live UI renders local belief only.** The objective board must never reach a render call.
6. **No magic numbers.** Every quantitative value comes from the config, which derives from Appendix F.
7. **Python decides the move. Always.** The LLM writes only the verbal hint.
8. **Over-the-wire game messages are free natural language.** No coordinates, no numeric position protocol.
9. **Everything a peer sends is untrusted** and is validated before touching state.
10. **Secrets never enter git.** Not the working tree, not the history.

## House rules for working in this repo

- **Build one layer at a time**, in the order set by `PLAN.md` §5. Do not start a layer before the previous one has been observed running end-to-end. Skipping turns a one-variable bug hunt into an unsolvable multi-variable one.
- **A layer is done when the behaviour was watched by a human** — not when the code compiles and not when tests pass alone.
- **Write at least one test per layer that proves rejection**, not just acceptance. A verifier that has never rejected anything is indistinguishable from a broken one.
- **Keep modules short** — 150 lines is a hard cap (`software_submission_guidelines-V3.pdf` §3.2), not a target. When a file grows past it, split by one of: extracting a shared helper into its own file, extracting a mixin, a 50/50 read/write split, or extracting constants/models into their own file. All configuration external.
- **Every function, class, and module under `src/` gets a docstring** explaining *why*, not what — `software_submission_guidelines-V3.pdf` §3.3/§20.2 requires this project-wide; it overrides the terser no-comments default for this repo specifically.
- **Run `spec-guard` before every commit.** It is a skill in `.claude/skills/spec-guard/`.

## Commands

```bash
uv sync

# run this peer — role is fixed by which repo you are in, not a flag
# (rules 1/2: this package must never be able to import a thief brain)
uv run python -m cop peer

# replay and verify a recorded match
uv run python -m cop replay --log logs/log_<game_id>_g<NN>.json

# tests
uv run pytest

# validate config against the mandatory parameter table
python .claude/skills/spec-guard/scripts/check_config.py config/shared/config_<game_id>_g<NN>.json

# confirm both teams' configs are byte-identical (fatal rule 11)
python .claude/skills/spec-guard/scripts/check_config.py --identical ours.json theirs.json

# secret sweep - must return nothing
git log --all --full-history -- '*credentials*' '*token.json*' '*.env'
```

## The fourteen zeroes

Any one of these scores nothing regardless of match results. Full list with sanctions in `.claude/skills/spec-guard/references/RULES.md`.

1. Cop and thief sharing a process or live state (1, 2)
2. Live GUI showing the objective board (8, 9)
3. Config not byte-identical, or a minimum lowered (11, 12)
4. Undeclared or misdeclared barrier (15, 16)
5. No SHA-256 commit-reveal (17)
6. Nonce leaked before game end, or from `random` instead of `secrets` (18)
7. Any hash mismatch at audit (19)
8. No replay verifier app (20)
9. Lying about a capture, in either direction (21, 22)
10. Scent model not cryptographically locked pre-game (23)
11. Numeric position protocol instead of natural language (27)
12. Gmail scope wider than send-only (30)
13. A secret in the repo or in git history (39)
14. Reports missing or contradictory between the two teams (34, 35)

## A second governing document

`software_submission_guidelines-V3.pdf` is a generic professional-software standard the course also grades against, independently of the 55 book rules. It adds requirements the book never mentions: `docs/PRD.md` + `docs/PLAN.md` + `docs/TODO.md` under `docs/`, ≥85% test coverage, zero `ruff check` violations, an SDK-facade architecture, and docstrings on every function/class/module. Where it gives a number that conflicts with Appendix F (e.g. its illustrative Gatekeeper config), **Appendix F wins** — the guide's numbers there are illustrating the pattern's shape, not overriding the game's locked parameters.

## Known trap

PRD 2 deliberately sends bare coordinates over localhost. That is legal only while the language layer does not exist. **PRD 4 must remove it** — rule 27 is fatal, and this is exactly the kind of scaffolding that survives quietly into a real match. Grep the wire before the first counted game.

## Where the numbers live

`.claude/skills/spec-guard/references/PARAMETERS.md` is the only source of truth for quantitative values. Never copy a number from the book body, from a figure, or from the reference repo. Defaults: 7×7 board, 14 barriers, 35-step ceiling, 35-step survival threshold, scent 0.9 / 0.10 decay / 5×5 window, capture 20-5, survival 5-10, 6 sub-games per series.
