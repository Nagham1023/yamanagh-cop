# PRD 13 — ML Pipeline Orchestration & Human-Gated Deployment

Status: **Built & verified through the gate; the promotion commit itself is intentionally not made by this layer.** Built via `TODO13.md`, verified by `tests/unit/` (33 new tests, ~99% coverage on every new module — see "Also verify" for the two pre-existing lines this doesn't cover), a live, real run of the full pipeline (`train` → `evaluate` → `quantize` → `benchmark`, and a real bounded `refine` search that converged on round 1), a real scoped `rule-auditor` pass, and a real `ml-promotion-gate` verdict (`PASS`, with an honest caveat about eval sample size). `ruff check` clean.

**The one thing this PRD deliberately does not do**: create `training/promoted/` or make the commit that flips `RLCopBrain` to be the default. That is the plan's own explicit human checkpoint (`PLAN.md` §8's extended table, "Approving the promotion commit itself") — Claude built and ran everything up to a real, current `PASS` verdict, and stops there.

## Built & verified

A real end-to-end run, not a synthetic example:

```
uv run python scripts/ml/orchestrate_pipeline.py --stage refine --run-id-prefix prd13_candidate
  -> converged=True rounds_run=1 best_run_id=prd13_candidate_round1 (win_rate=1.0, episode_count=2000)
uv run python scripts/ml/orchestrate_pipeline.py --stage quantize --run-id prd13_candidate_round1
uv run python scripts/ml/orchestrate_pipeline.py --stage benchmark --run-id prd13_candidate_round1
```

Then a scoped `rule-auditor` pass against `rl_cop_brain.py`/`rl_checkpoint.py`/`rl_checkpoint_quant.py`/`strategy_loader.py` — **CLEAN**, no fatal or non-fatal violations, rule 25/I7 verified live against the current on-disk state, docstring discipline (the thing PRD 11/12's audits each had to fix) confirmed still holding via an AST walk.

Then a real `ml-promotion-gate` invocation against `prd13_candidate_round1`, reading real artifacts:

```
win-rate: 1.00 vs. target 0.60 — PASS, with an honest caveat: the eval pass is
  only 20 episodes and both RLCopBrain and baseline CopBrain reach 100% capture
  against a weak random-walk thief — the real differentiator is speed
  (rl_avg_steps_to_capture=8.8 vs. baseline's 10.05), not capture rate itself.
latency margin: p99 12.10us, budget 30s -> 2,478,520x margin — PASS
quantization: 91.22% argmax-agreement, 40.95% size reduction — SURFACED, not
  auto-accepted; a human's call per PLAN.md §8's own checkpoint.
rule-25/I7: current, scoped rule-auditor pass — CLEAN.

VERDICT: PASS.
```

This is the honest, real state of a genuine promotion candidate today — not a fabricated success story. The gate agent's own caveat (thin eval sample, capture-rate ties at the ceiling against an easy opponent) is exactly the kind of finding this whole layer exists to surface rather than paper over, and it's recorded here rather than smoothed into a cleaner-sounding summary.

The two-process milestone itself, `scripts/watch_prd13_rl_deployment.py`, is watched and passes reliably (confirmed across repeated runs): two real, independent `run_peer()` calls, one side's `police_class` pointing at `RLCopBrain`, both sides negotiate Step-0, commit/reveal for real, and reach a completed, reported match (`WAITING_FOR_OPPONENT`, not `TECHNICAL_LOSS`) — proving the dynamic loader wires a real RL brain through the actual CLI path, not a hand-assembled `Orchestrator`. Building this milestone surfaced a real, pre-existing, unrelated bug — see the dedicated section below.

## Design

### Rules owned (the one layer that touches the real match path)

| Rule/Invariant | Satisfied by |
|---|---|
| 25 / I7 | `rule-auditor`, scoped to the four RL files, verifies the deployed decision stays deterministic/legality-masked/pure-Python — not re-derived by `ml-promotion-gate`, which requires that report rather than re-checking it itself. |
| I2 (rule 3) | `strategy_loader.load_brain_class` is the one and only dynamic brain loader anywhere under `src/` — confirmed by a repo-wide grep for `importlib`/`import_module` during the scoped audit; `promotion_guard.py` imports `RLCopBrain` statically, it does not compete as a second loader. |
| I6 | `config/rl_training.toml` stays private tuning, confirmed to never enter `config/shared/`'s byte-identical check (no file under `config/shared/` changed in this diff). |
| 42 | `README.md` §4 and `docs/EXPERIMENT_REPORT.md` are **not yet updated** by this PRD — that is `ml-experiment-reporter`'s job, and its own agent definition requires a `PASS` verdict before it runs. A `PASS` now exists; the report-writing invocation is a follow-up action, not bundled into this build pass (see "What's left" below). |

### Deployment mechanism — built exactly as designed, verified as safe pre-promotion

```python
# src/cop/shared/strategy_loader.py
def load_brain_class(dotted_path: str) -> type[BrainBase]: ...
```

`src/cop/cli_peer_build.py` (split out of `cli_peer.py` to stay under the 150-line cap once this wiring landed — `cli_peer.py` was 180 lines with the inline version, 149 after the split):

```python
brain_cls = load_brain_class(private_config.police_class) if private_config.police_class else CopBrain
```

**Confirmed live, not assumed**: `config/game.toml`'s `[strategy] police_class` line is still commented out — `test_no_police_class_set_still_constructs_a_cop_brain_default` reads the real file directly and asserts `CopBrain` is still what gets constructed. This is the actual, currently-live behavior of this repo today, not a hypothetical default.

**Sequencing** (as planned): this PRD builds the loader, the guard, and the pipeline with `CopBrain` still the real default. The separate promotion commit that would ever flip that default — by either promoting `training/promoted/` and later making `police_class`'s *absence* mean `RLCopBrain` (the plan's original auto-replace design), or any equivalent mechanism — is not made here. It requires: `ml-promotion-gate` PASS (have it, for `prd13_candidate_round1`), a current scoped `rule-auditor` pass (have it), and a human reading both and approving the commit itself (does not yet exist — this is the explicit, intentional stopping point).

### Hard runtime guard — the auto-replace fork's safety net, built and tested

```python
# src/cop/shared/promotion_guard.py
def require_fresh_promotion_report_for_counted_game(brain: BrainBase, *, counted: bool) -> None: ...
```

Called at the top of `cli_peer.py::_run_match_body`. Only ever activates for `counted=True` **and** `isinstance(brain, RLCopBrain)` — every other case (uncounted games, any non-RL brain including the current real default `CopBrain`) is untouched, verified by 6 tests including both "never triggers" cases explicitly, not just the triggering ones. Since `training/promoted/promotion_report.json` doesn't exist yet (no promotion has happened), a counted game against a hypothetically-wired `RLCopBrain` today would correctly refuse to start — the guard is live and correct even before its first real use.

## Explicitly out of scope

- Making the promotion commit itself — see "Built & verified" above and `PLAN.md` §8's checkpoint table.
- `ml-experiment-reporter`'s actual invocation — its own definition requires a `PASS`, which now exists, but running it (and thereby editing `docs/EXPERIMENT_REPORT.md`/`README.md`) is a deliberate follow-up action, not bundled into the build-and-gate pass this PRD covers.
- Auto-retraining or any training during a real match series — offline-only, unchanged from PRD 11/12.
- Multi-brain ensembling or runtime brain switching mid-series.
- Unit tests for `scripts/ml/orchestrate_pipeline.py` itself — `scripts/` has no existing precedent in this repo of being imported/unit-tested (every `watch_prd*.py` file is a standalone, human-watched demo). The CLI wrapper is ~75 lines of argparse+dispatch with all its substantial logic already covered by `training/pipeline/`'s own tests; its own argument-validation paths (missing `--run-id`, missing `--run-id-prefix`, unknown `--stage`) were verified by direct manual invocation instead, each producing the correct exit code.

## Design Question 1 — where does `training/pipeline/` actually live?

The approved plan proposed `scripts/ml/pipeline_stages.py`/`refinement_loop.py`/`artifacts.py` as the substantial, testable logic. Building it surfaced a real problem: `scripts/` is not an installed or otherwise-importable package anywhere in this repo (`pyproject.toml` never lists it, no `__init__.py` exists, and no test file anywhere imports from it) — every existing script assumes direct execution only. Since PRD 13's own scope explicitly requires unit-testing the refinement loop's cap/criterion/budget independently (not just watching a demo), that logic needed to be properly importable.

**Corrected during the build, not assumed at design time** (the same category of correction PRD 11's clamp-radius design question already normalized for this project): the substantial logic moved into `training/pipeline/` — already a sandbox-only, properly-packaged, one-directional-dependency-on-`src/cop/` location (PRD 11's own `training/` package, extended). `scripts/ml/orchestrate_pipeline.py` stays exactly the thin CLI wrapper the plan intended, importing from `training.pipeline`, mirroring this repo's own established `__main__.py`-vs-`cli_peer.py` split precedent. Nothing about the plan's *behavior* changed — every `--stage` choice, every artifact file, the bounded-loop discipline — only where the reusable code physically lives.

## Found while building the real two-process milestone — a pre-existing bug, not this layer's

`scripts/watch_prd13_rl_deployment.py`'s first two draft configs (`max_moves=4`, then `max_moves=15`, both with barriers enabled) reliably reproduced a real, mutual `TECHNICAL_LOSS`: both sides' trace logs show `unexpected_capture_claim_received` followed by `technical_loss ... AWAITING_REVEAL` at the same point in the exchange. Root cause, confirmed by reading both sides' full traces side by side: when **both** peers place a barrier (or land a `Move` on their believed target) on an overlapping turn, **each sends its own outgoing Capture Claim while simultaneously receiving the peer's** — and the orchestrator's capture-claim handling doesn't have a path for "I'm already awaiting a response to my own claim, and I've also just received one." Both sides then wait out the full `response_timeout_seconds` for a reply that was never coming, and both reach `TECHNICAL_LOSS`.

This is **not** an RL/quantization/pipeline bug — both sides in this reproduction run plain `CopBrain`-lineage barrier/capture logic, completely unchanged by PRD 11-13 (`RLCopBrain` overrides only `_pick_move`). It is a pre-existing concurrency gap in the capture-claim protocol itself (PRD 6/8 territory), surfaced here only because this milestone's own test harness runs **two symmetric `CopBrain`-lineage sides against each other** — the only kind of opponent available without a second, real thief process (the same constraint `tests/unit/test_cli_peer.py`'s own docstring already names) — which converges the two sides onto each other unusually fast compared to a real cop-vs-thief match, where a genuinely evading thief would rarely trigger simultaneous mutual claims.

**Fixing the orchestrator's capture-claim concurrency handling is out of scope for this ML-pipeline PRD** — it would be a real, separate PRD 6/8 fix, not a quantization/deployment-gating concern, and taking it on here would be exactly the kind of scope creep `PLAN.md`'s own layering discipline exists to prevent. The milestone script instead routes around it (`max_moves=2`, matching `test_cli_peer.py::_fast_shared_config`'s own exact precedent and stated reason; `max_barriers=0`), and this finding is recorded here — the same "found only by actually running this layer" discipline every prior PRD's retrospective in this repo already follows — so a future PRD (or the reference audit) has the reproduction steps on record rather than rediscovering it from scratch.

## Design Question 2 — why does `run_train_eval_cycle` persist its own result?

The approved plan's artifact table implied `refinement_metrics.json` as a stage output, but the first implementation only printed the result and returned it in-process — a caller in a different process (the CLI's `--stage refine` invocation, or a later `ml-promotion-gate` reading artifacts cold) would have no way to see a completed search's outcome. Fixed by having `run_train_eval_cycle` call `write_stage_metrics(run_id_prefix, "refinement", ...)` itself before returning, on both the converged and cap-exhausted paths — confirmed by `test_the_result_is_persisted_as_an_artifact_readers_can_find_without_rerunning`, and by the real `ml-promotion-gate` run above, which read `training/runs/prd13_candidate/refinement_metrics.json` as its authoritative convergence signal exactly as designed.

## New Claude Code subagents & skill

`.claude/agents/ml-training-runner.md`, `ml-experiment-reporter.md`, `ml-promotion-gate.md` — all match `rule-auditor.md`'s frontmatter/procedure/reporting-format discipline. `ml-experiment-reporter` is the one documented deviation from the read-only-verdict posture (needs `Edit`, scope pinned to exactly two files) — stated explicitly in its own file, the same way `PLAN.md` documents its own deviations. `.claude/skills/ml-pipeline-guard/SKILL.md` — Mode-based, matching `spec-guard/SKILL.md`'s structure, five modes covering launch, monitor, pre-promotion gate, post-match rollback, and report assembly.

**All three agents and the skill were exercised for real this session**, not just written and left untested: the scoped `rule-auditor` pass and the `ml-promotion-gate` verdict above are genuine agent invocations against genuine pipeline artifacts, not illustrative examples.

## Also verify (acceptance criteria, checked once built)

- `strategy_loader.load_brain_class` rejects a malformed dotted path, an unimportable module, a missing attribute, and a real class that isn't a `BrainBase` subclass — 4 distinct rejection tests, plus 2 acceptance tests (loading `CopBrain` and `RLCopBrain` for real).
- `promotion_guard`'s guard never triggers for an uncounted game or a non-`RLCopBrain` brain (2 tests), and correctly raises for a missing report, a missing checkpoint, and a hash mismatch, and correctly passes for a matching fresh report (4 tests).
- `build_orchestrator` with no `police_class` set constructs `CopBrain` — checked against the real, current `config/game.toml`, not a synthetic stand-in.
- Every pipeline stage (`train`/`evaluate`/`quantize`/`benchmark`) is independently runnable and reads only the artifact the prior stage actually wrote, never re-deriving it.
- The refinement loop's cap, coverage criterion, and wall-clock budget are each independently proven: an unreachable target stops at exactly the cap (not more, not forever); a zero wall-clock budget stops before round 1 even starts; a non-monotonic win-rate sequence still returns the best round, not the last one blindly.
- No new magic numbers: `_EVAL_EPISODES`/`_BENCHMARK_SAMPLE_COUNT` in `training/pipeline/stages.py` are pipeline-tooling knobs (same category as PRD 12's `_LATENCY_SAMPLE_COUNT`), never Appendix F values.

**One real coverage gap, inherited not introduced**: `src/cop/cli_peer_build.py` sits at 89% coverage in isolated PRD-13 test runs — the two uncovered lines (default `log_path` construction, `league_ledger_path` override) are unmodified logic moved verbatim from the pre-PRD-13 `cli_peer.py`, and their coverage normally comes from `tests/unit/test_cli_peer.py`'s real two-subprocess test, which hangs in this sandbox environment (the same pre-existing, environment-specific issue PRD 11's own "Built & verified" section already documented and confirmed via `git stash` against a clean `main`).

## New dependency

None. Every new file (`strategy_loader.py`, `promotion_guard.py`, `cli_peer_build.py`, `training/pipeline/*.py`, `scripts/ml/orchestrate_pipeline.py`) is stdlib-only (`importlib`, `hashlib`, `json`, `dataclasses`, `time`, `argparse`) — the "zero new dependency" story holds through all three ML PRDs.

## What's left (not part of this build pass, by design)

1. Invoke `ml-experiment-reporter` against `prd13_candidate_round1` to actually write up `docs/EXPERIMENT_REPORT.md`/`README.md` §4 — it can run now, since a real `PASS` exists.
2. A human reads this PRD, the `rule-auditor` report, and the `ml-promotion-gate` verdict, and decides whether to create `training/promoted/` and make the promotion commit — see `PLAN.md` §8's extended checkpoint table.
3. One uncounted warm-up match, watched, before any counted game ever uses a promoted `RLCopBrain` — enforced structurally by `promotion_guard.py` for counted games, but still worth a human actually watching per `.claude/skills/ml-pipeline-guard/SKILL.md`'s Mode 3.

## Builds on

PRD 11's `training/` package and `RLCopBrain`/checkpoint format; PRD 12's quantization and latency-benchmark functions, reused as-is by `training/pipeline/stages.py`. `src/cop/cli_peer.py`/`cli_peer_build.py` extend PRD 10's CLI entry point without changing its default behavior. `.claude/agents/rule-auditor.md` is the template every new agent file matches, and the actual gate every promotion decision routes through.
