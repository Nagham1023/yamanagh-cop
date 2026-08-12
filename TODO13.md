# TODO13 — Build Checklist for PRD 13 (ML Pipeline Orchestration & Human-Gated Deployment)

Status: **Built & verified through the gate; promotion commit intentionally not made.** Read `PRD/PRD-13-ml-pipeline-and-deployment.md` in full first — its Design Questions record two real corrections made during the build (where `training/pipeline/` actually lives; why the refinement loop persists its own result), and its own "Found while building the real two-process milestone" section records a real, pre-existing, unrelated bug found and routed around, not fixed.

## 1. `src/cop/shared/strategy_loader.py` — the dynamic loader

- [x] `load_brain_class(dotted_path) -> type[BrainBase]` — Table 22's `"package.module:Class"` format, validates a real `BrainBase` subclass, raises `ValueError` (never a silent fallback) on any failure shape.
- [x] Rejection tests: missing colon, empty string, missing class name, missing module name, unimportable module, attribute not found, a real class that isn't a `BrainBase` subclass — 7 distinct rejection cases.
- [x] Acceptance tests: loads real `CopBrain` and real `RLCopBrain`.

## 2. `src/cop/cli_peer_build.py` — `build_orchestrator`, split from `cli_peer.py`

- [x] `police_class` (parsed since PRD 4, unused until now) finally consumed: `load_brain_class(...)` if set, else `CopBrain` — `CopBrain` stays the real, live default (confirmed against the actual current `config/game.toml`, not assumed).
- [x] Split out of `cli_peer.py` — the file hit 180 lines with the inline version; 149 after the split, `cli_peer_build.py` at 47.
- [x] Test: no `police_class` set still constructs `CopBrain`, checked against the real repo config file directly.
- [x] Test: `police_class` set to `RLCopBrain`'s dotted path actually loads it.

## 3. `src/cop/shared/promotion_guard.py` — the hard runtime guard

- [x] `require_fresh_promotion_report_for_counted_game(brain, *, counted)` — only ever active for `counted=True` **and** `isinstance(brain, RLCopBrain)`; every other case is a silent no-op.
- [x] Raises `StalePromotionError` on: missing report, missing checkpoint file, or a hash mismatch between the report's recorded `checkpoint_sha256` and the actual file on disk.
- [x] Wired into `cli_peer.py::_run_match_body`, checked before the server thread even starts.
- [x] 6 tests: both "never triggers" cases (uncounted; non-RL brain) explicitly, plus missing-report/missing-checkpoint/stale-hash/matching-fresh-report for the triggering case.

## 4. `training/pipeline/` — the pipeline's substantial, testable logic

- [x] **Design correction, recorded not hidden**: moved here from the plan's original `scripts/ml/` location — `scripts/` has no existing import/test precedent in this repo; `training/` already does. `scripts/ml/orchestrate_pipeline.py` stays the thin CLI wrapper the plan intended.
- [x] `artifacts.py` — `run_dir` (self-creating), `checkpoint_path`, `quantized_checkpoint_path`, `write_stage_metrics`/`read_stage_metrics`/`stage_metrics_exist`. **Found only by running it**: `checkpoint_path`/`quantized_checkpoint_path` didn't ensure the run directory existed before a stage tried to write into it (only `write_stage_metrics` did) — a real `FileNotFoundError` on the very first smoke test, fixed by making `run_dir` itself idempotently create the directory.
- [x] `stages.py` — `run_train`/`run_evaluate`/`run_quantize`/`run_benchmark`, each writing exactly one artifact, each reading only what the prior stage wrote (never re-deriving). `run_evaluate` compares `RLCopBrain` vs. baseline `CopBrain` capture rate and avg-steps-to-capture against the same seeded random-walk opponents.
- [x] `refinement_loop.py` — `run_train_eval_cycle`: hard iteration cap, explicit numeric coverage criterion, wall-clock budget checked before each round. **Design correction, recorded not hidden**: the first draft only returned its result in-process; fixed to also persist it via `write_stage_metrics(run_id_prefix, "refinement", ...)` on both the converged and cap-exhausted paths, so a cold reader (a later process, an agent) can find a completed search's outcome without re-running it.
- [x] Tests: 5 stage tests (each stage runnable standalone, correct artifact shape) + 6 refinement-loop tests (trivial convergence on round 1; an *unreachable* target proven to stop at exactly the cap, not more, not forever; each failing round doubles `episode_count` by a fixed rule; a zero wall-clock budget stops before round 1 even starts; the cap-exhausted case returns the *best* round, not the last blindly; the persisted artifact matches the in-process result).

## 5. `scripts/ml/orchestrate_pipeline.py` — the thin CLI wrapper

- [x] `--stage {train,evaluate,quantize,benchmark,all,refine}`, dispatching into `training.pipeline`.
- [x] No unit tests (see PRD's own "Explicitly out of scope" — `scripts/` has no test precedent in this repo); verified instead by direct manual invocation: missing `--run-id` → exit 2 with a clear message; missing `--run-id-prefix` for `refine` → exit 2; unknown `--stage` → argparse's own rejection.
- [x] Run for real, `--stage all` and `--stage refine` both, against the real repo config — see PRD's "Built & verified" for the actual numbers produced.

## 6. `.gitignore` — `training/runs/`

- [x] Added — bulk, per-run artifacts, not secrets, just build-artifact noise. `training/promoted/` (the one gated, committed checkpoint, not created by this PRD) is deliberately **not** covered.

## 7. The three agents + skill

- [x] `.claude/agents/ml-training-runner.md` — matches `rule-auditor.md`'s frontmatter/procedure/reporting-format exactly; explicitly states it's never invoked for a clean run.
- [x] `.claude/agents/ml-experiment-reporter.md` — the one documented `Edit`-access deviation, scope pinned to exactly two files, requires a `PASS` verdict before it will act.
- [x] `.claude/agents/ml-promotion-gate.md` — the final reviewer; requires (never re-derives) a current, correctly-scoped `rule-auditor` pass; distinguishes `BLOCKED` (missing precondition) from `FAIL` (a real number didn't clear its threshold); never writes `training/promoted/`, never makes the promotion commit.
- [x] `.claude/skills/ml-pipeline-guard/SKILL.md` — 5 modes matching `spec-guard/SKILL.md`'s structure (launch, monitor, pre-promotion gate, post-match rollback, report assembly).
- [x] **All three agents and the skill were exercised for real**, not just written: a real scoped `rule-auditor` pass (CLEAN, no violations) and a real `ml-promotion-gate` verdict (`PASS`, with an honest thin-sample caveat) against real pipeline artifacts from a real `--stage refine` run.

## 8. The real end-to-end run

- [x] `uv run python scripts/ml/orchestrate_pipeline.py --stage refine --run-id-prefix prd13_candidate` → converged round 1, `win_rate=1.0` against `win_rate_target=0.6`.
- [x] `quantize`/`benchmark` run on the winning round → 91.22% argmax-agreement, 40.95% size reduction, p99 latency 2,478,520x under the response-timeout budget.
- [x] Scoped `rule-auditor` pass against the four RL files → CLEAN.
- [x] `ml-promotion-gate` invocation against the real artifacts → `PASS`, with the win-rate caveat recorded verbatim in the PRD.

## 9. `scripts/watch_prd13_rl_deployment.py` — the milestone demo

- [x] Two real, independent `run_peer()` calls, one side's `police_class` pointing at `RLCopBrain`.
- [x] **Found only by actually running this milestone**: the first two draft configs (`max_moves=4`, then `15`, both with barriers enabled) reliably reproduced a real, pre-existing, unrelated mutual `TECHNICAL_LOSS` bug — full root-cause analysis and reproduction steps in `PRD/PRD-13-ml-pipeline-and-deployment.md`'s own dedicated section. Routed around (`max_moves=2` matching `test_cli_peer.py`'s own exact precedent and reason; `max_barriers=0`), not fixed — recorded as a known issue in `TODO.md`'s cross-cutting section for a future PRD.
- [x] Run and watched, repeated: both sides reach `WAITING_FOR_OPPONENT` (a completed, reported match), `RLCopBrain` confirmed as the RL side's actual brain class — reliably reproducible across multiple runs, not a one-off.

## Cleanup and final verification

- [x] Every new/changed file checked against the 150-line house cap: `strategy_loader.py` 42, `cli_peer_build.py` 51, `cli_peer.py` 148 (down from 180), `promotion_guard.py` 55, `training/pipeline/{__init__,artifacts,stages,refinement_loop}.py` all under 130, `scripts/ml/orchestrate_pipeline.py` 75, `scripts/watch_prd13_rl_deployment.py` 145.
- [x] `uv run ruff check` on every new/changed file — clean.
- [x] `uv run pytest` on the new PRD-13 suite: 33 tests (27 from the initial build + 6 already counted in the scoped-audit's own run), ~99% coverage (the two uncovered lines in `cli_peer_build.py` are unmodified pre-existing logic, see the PRD's own account).
- [x] Full existing suite spot-checked for regressions on `cli_peer`-adjacent tests (`test_main_cli.py` — 7 passed; `test_cli_peer.py` — collects cleanly, not run directly per the user's own standing instruction to leave that hanging sandbox issue alone).
- [x] **Found only by the final full-layer `rule-auditor` pass, not the earlier 4-file scoped one**: `promotion_guard.py`'s `require_fresh_promotion_report_for_counted_game`, `cli_peer_build.py`'s `build_orchestrator`, and `cli_peer.py`'s `_run_match_body`/`match_fn` (nested) were all missing docstrings — the scoped audit's "docstring discipline held" claim was accurate for the exact 4 files it covered (`rl_cop_brain.py`/`rl_checkpoint.py`/`rl_checkpoint_quant.py`/`strategy_loader.py`), but didn't extend to these three files it never looked at. Fixed; `cli_peer.py` trimmed elsewhere (its own module docstring, deduplicating detail `_run_match_body`'s new docstring now covers) to land back at 148 lines. Re-ran ruff and the full test suite after the fix — still clean, still green.
- [x] `git log --all --full-history -- '*credentials*' '*token.json*' '*.env'` — still empty.
- [x] `rule-auditor` full pass — see `PRD/PRD-13-ml-pipeline-and-deployment.md`'s Status line and this file's own §8.
- [x] `TODO.md`'s own master checklist — PRD 13 row added, plus the known-issue line in Cross-cutting/submission.
- [x] `PRD/PRD-13-ml-pipeline-and-deployment.md` written, built, and verified against this checklist; commit — **without** `training/promoted/` or a promotion commit, both deliberately left for a human.
