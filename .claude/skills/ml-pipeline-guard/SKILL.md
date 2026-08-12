---
name: ml-pipeline-guard
description: Run, monitor, and safely gate promotion of the RL movement-policy pipeline (PRD 11/12/13 — tabular Q-learning, quantization, deployment). Use before launching a training/refinement run, when interpreting a run's metrics artifacts, before editing anything that would promote a checkpoint, after a real or warm-up match used RLCopBrain, and before folding results into the submission report.
---

# ml-pipeline-guard

The failure mode this skill exists to prevent is not a training run that crashes — those are loud and obvious. It's a checkpoint that trains cleanly, quantizes cleanly, benchmarks well under budget, and is still the wrong thing to deploy, because nobody actually read `evaluate_metrics.json`'s win-rate against the threshold, or the `quantize_metrics.json` accuracy trade-off, before `RLCopBrain` became the default a real (possibly counted) match plays with.

## Sources of truth

1. **`PRD/PRD-11-rl-training-simulator.md`, `PRD-12-quantization-and-benchmarking.md`, `PRD-13-ml-pipeline-and-deployment.md`** — the full design rationale for every stage below.
2. **`training/runs/<run_id>/*_metrics.json`** — the only place a real, measured number for this pipeline lives. Never trust a printed number from an old terminal scrollback over the artifact file.
3. **`.claude/agents/{ml-training-runner,ml-experiment-reporter,ml-promotion-gate}.md`** — what each agent actually checks and refuses to check. This skill tells you *when* to invoke them; those files are the authority on *what* they do.

## When to run which mode

| Situation | Mode |
|---|---|
| About to launch a training/refinement run | Mode 1 — Launch a stage |
| A run is in progress or just finished | Mode 2 — Monitor & interpret metrics |
| About to promote a checkpoint (create `training/promoted/`, make the promotion commit) | Mode 3 — Pre-promotion gate |
| `RLCopBrain` is deployed and a real/warm-up match just used it | Mode 4 — Post-match rollback check |
| About to fold results into the submission report | Mode 5 — Report assembly check |

---

## Mode 1 — Launch a stage

```bash
uv run python scripts/ml/orchestrate_pipeline.py --stage train --run-id <id>
uv run python scripts/ml/orchestrate_pipeline.py --stage evaluate --run-id <id>
uv run python scripts/ml/orchestrate_pipeline.py --stage quantize --run-id <id>
uv run python scripts/ml/orchestrate_pipeline.py --stage benchmark --run-id <id>
uv run python scripts/ml/orchestrate_pipeline.py --stage all --run-id <id>          # one full pass, no search
uv run python scripts/ml/orchestrate_pipeline.py --stage refine --run-id-prefix <p>  # bounded search, PLAN §6 discipline
```

A clean run (`--stage all` or `--stage refine`) prints each stage's payload and exits 0 (or 1 for `refine` if it didn't converge within its cap — not itself an error, a real, documented outcome). **Invoke `ml-training-runner` only if the printed output looks anomalous** (flat/declining reward, a non-`0` exit you don't understand) — per `PLAN.md` §6's dynamic-selection responsibility, a clean run needs no agent call at all.

## Mode 2 — Monitor & interpret metrics

Every stage writes exactly one file under `training/runs/<run_id>/`:

| File | What it means |
|---|---|
| `train_metrics.json` | `episode_count`, `final_epsilon`, `reward_history`, `states_visited` |
| `evaluate_metrics.json` | `rl_capture_rate`, `baseline_capture_rate`, `*_avg_steps_to_capture`, `win_rate_vs_baseline` |
| `quantize_metrics.json` | `argmax_agreement_rate`, `size_before_bytes`, `size_after_bytes`, `size_reduction_fraction` |
| `benchmark_metrics.json` | `p50/p95/p99_seconds`, `response_timeout_seconds`, `margin_multiple` |
| `refinement_metrics.json` | (only for `--stage refine`) `best_run_id`, `rounds_run`, `converged`, `refinement_log` |

Thresholds worth eyeballing before invoking any agent: `win_rate_vs_baseline` against `config/rl_training.toml`'s `win_rate_target`; `margin_multiple` should be many orders of magnitude for the tabular fork (see PRD 12's own honest framing — anything close to 1 is a red flag worth investigating, not expected); `argmax_agreement_rate` below ~0.95 is worth a human's attention before Mode 3.

## Mode 3 — Pre-promotion gate

Checklist, mirroring `spec-guard`'s own Mode 3 shape:

- [ ] `ml-promotion-gate` invoked against the candidate `run_id` and returned `PASS` (not `BLOCKED`, not `FAIL`).
- [ ] The `rule-auditor` pass `ml-promotion-gate` required is genuinely current — its own report states the checkpoint/commit it was scoped against.
- [ ] A human has read `quantize_metrics.json`'s `argmax_agreement_rate` themselves and accepted it explicitly — this is never a threshold either agent picks unilaterally (`PLAN.md` §8's own checkpoint table).
- [ ] `training/promoted/rl_cop_qtable.json` + `training/promoted/promotion_report.json` (with a `checkpoint_sha256` matching the promoted file) are the **only** change in the promotion commit's diff — no accidental source edits riding along.
- [ ] One **uncounted** warm-up match run and watched first — never a counted game as the first real use of a newly-promoted checkpoint. `src/cop/shared/promotion_guard.py` enforces this can't be skipped for counted games structurally, but a human should still watch the warm-up, not just let the guard pass mechanically.
- [ ] The human who approves the promotion commit is the same checkpoint named in `PLAN.md`'s extended human-in-the-loop table — Claude never makes this commit unprompted, ever, under any instruction short of the user explicitly directing it after reading the gate's verdict.

## Mode 4 — Post-match rollback

Rollback for the auto-replace fork specifically means setting `[strategy] police_class = "cop.reasoning.cop_brain:CopBrain"` in `config/game.toml` — this is now the opt-*out*, not the opt-in it would be under the alternative deployment posture. Never a code revert; the loader and the promoted checkpoint both stay valid for next time. Confirm via `uv run python -c "from cop.shared.private_config import PrivateConfig; print(PrivateConfig.from_file('config/game.toml').police_class)"` that it now reads the heuristic path, not `None` and not `RLCopBrain`'s.

## Mode 5 — Report assembly check

- [ ] `ml-experiment-reporter` actually ran — `git diff` shows both `docs/EXPERIMENT_REPORT.md` (a new numbered section) and `README.md` (§4 no longer says "Not built") touched together, not just one.
- [ ] Spot-check 2-3 numbers in the written report against their source `training/runs/<run_id>/*_metrics.json` files directly — a cheap, mandatory cross-check the same way `spec-guard` Mode 4's secret sweep is cheap and mandatory regardless of what else changed.
- [ ] Confirm the report states the real, possibly-unflattering numbers (e.g. a sub-100% argmax-agreement, or a win-rate that ties the baseline on capture-rate and only differentiates on speed) rather than a rounded or selectively-quoted version.

---

## The one thing that carries real risk here

Under this repo's chosen auto-replace deployment posture, **the promotion commit is the single moment a bad RL policy could reach a real match with no human gesture in between** unless every step above was actually followed. `src/cop/shared/promotion_guard.py`'s hard runtime check only ever verifies a report *exists and matches the checkpoint on disk* — it has no opinion on whether the checkpoint is any good. That opinion lives entirely in Mode 3 above, and in the human who reads `ml-promotion-gate`'s verdict before the commit is made.
