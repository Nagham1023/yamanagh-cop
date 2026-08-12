# PRD 14 — Belief-Aware State, Barrier-Placement RL, and Pipeline Provenance

Status: **Built & verified.** Refines and extends PRD 11-13 per a user-supplied optimization proposal, itself refined against the book/architecture before building — two of the proposal's pieces directly reversed a PRD-11 design decision (deliberately, with explicit approval), one piece was rejected outright (see "Rule-25-in-evaluate" below), and one was corrected mid-plan (the quantization fix is per-row, not "QAT" — a neural-network technique with no clean tabular analogue). Approved plan: `sprightly-spinning-fog.md`. Nothing from this layer is wired into any real match — same "built, tested, and left inert for now" posture PRD 11 itself established for the whole `RLCopBrain` class.

Built via seven ordered sub-tasks, each verified (tests green, a real training/pipeline run inspected) before the next started — this repo's own layer discipline, applied inside a single PRD rather than across PRDs, since every sub-task shares the same state-encoding/checkpoint-format surface and building them out of order would make a regression multi-variable to diagnose.

## Built & verified

A real end-to-end pipeline run against the actual production config (`config/shared/config_dev_g01.json`, 2000 episodes, real hyperparameters), after every sub-task below had already landed:

```
uv run python scripts/ml/orchestrate_pipeline.py --stage all --run-id <verify> --config config/shared/config_dev_g01.json
train:     states_visited=2424, reward_history tail healthy (first-10% avg 9.6 -> last-10% avg 11.3+)
evaluate:  win_rate_vs_baseline=0.75 (ground truth), win_rate_vs_baseline_belief_aware=0.25
           (RL beats the naive heuristic's 0.0 belief-aware capture rate under genuine uncertainty)
quantize:  argmax_agreement_rate=1.0, size_reduction_fraction=-0.054 (honestly negative, not smoothed over)
benchmark: p99=16.8us, margin_multiple=1,790,083x under the 30s response_timeout_seconds budget
```

`uv run pytest tests/unit/` — full suite, batched (this repo's own real-HTTP-server tests are slow/flaky as one invocation, documented in `instructions.md` §1): 632 passed, 2 pre-existing failures confirmed identical on a clean pre-PRD-14 baseline via `git stash` (`test_cost.py::test_a_real_take_turn_logs_a_zero_token_hint_generated_event`, `test_step_index_agreement.py::test_a_failed_attempt_does_not_advance_one_sides_step_count_without_the_other_knowing`) — not introduced here. `ruff check .` clean except one pre-existing, unrelated `SIM105` finding in `live_gui.py` (last touched in an unrelated commit).

## Design

### Rules owned

| Rule/Invariant | Satisfied by |
|---|---|
| 25 / I7 | `RLCopBrain._decide_move` (new this PRD) re-checks every ranked action live before returning it — a move against a Python-computed legal set, a barrier against `BarrierSet.can_place` — exactly the same discipline `_pick_move` already held for movement alone. See "Rule-25-in-evaluate" below for why this stays a static code-shape property, never a runtime metric. |
| 46 | `apply_cop_action`'s barrier branch checks `is_barrier_capture` unconditionally against the *true* `thief_pos`, never gated on belief — mirrors `run_local_subgame`'s own check exactly, now reachable in `SelfPlayEnv` for the first time. |
| 47 | `SelfPlayEnv.step`'s capture check became the same three-way check (coordinate, barrier, imprisonment) `run_local_subgame` already used — a real, found-not-assumed physics gap: before sub-layer B, rule 47 was structurally unreachable in `SelfPlayEnv` (no barriers ever existed to imprison anyone against). |
| I6 | `_bucket_barrier_count` is quota-*relative* (`<=quota/3`/`<=2*quota/3`/else), not a hardcoded literal boundary — `max_barriers` is a Table 15 minimum, negotiable upward. |

### Sub-layer A — belief-based state encoding

`State` grew a confidence bucket (`tuple[int,int,int,int]` -> now `tuple[int,int,int,int,int,int]` after sub-layer B). `SelfPlayEnv` now advances a real `BeliefTracker` (a scent field + belief map, the same two objects a live turn updates) every step and encodes its *estimate*, never ground truth — closing a real train/inference mismatch nobody had tested before: `RLCopBrain` always received the belief map's guess at real-match time (via `ground_truth_target_position`'s seam), but training saw perfect information throughout PRD 11/12/13.

`RLCopBrain` gained an optional `belief_confidence_provider` seam (keyword-only, defaulted to a callable-free `1.0`), deliberately left unbound at every real call site — confirmed decision, matching the exact "seam now, plug in later" shape `reasoning/state.py::ground_truth_target_position` already established. A new, additive `run_evaluate_belief_aware` stage drives `RLCopBrain._pick_move` directly through `SelfPlayEnv` (never touching the existing ground-truth-only `run_evaluate`/`subgame.py`), writing `win_rate_vs_baseline_belief_aware` alongside the existing metric in the same `evaluate_metrics.json`. Real result: the trained policy handles genuine uncertainty measurably better than blind pursuit (0.35 vs. 0.0 capture rate on the sub-layer-A-only checkpoint), even though its own ground-truth win-rate dipped slightly (1.0 -> 0.85) — an honest, reported side effect of confidence defaulting to `1.0` regardless of actual distance, not smoothed over.

### Sub-layer B — barrier-placement RL

`State` grew barrier-count and enclosure buckets. `SelfPlayEnv` now simulates real `BARRIER_<dir>` actions (the cop's four orthogonal neighbours, matching `CopBrain._barrier_candidates`' own shape) through the real `BarrierSet`, at the real `barrier_quota`. `RLCopBrain._decide_move` is overridden for the first time — previously fully inherited from `CopBrain` — so the Q-table now drives the barrier-vs-move choice too, falling back to `CopBrain`'s full heuristic on a genuine table miss. Checkpoint version bumped to `"v3"`; both a real `"v1"` and a real `"v2"` file now fail closed, verified against real file shapes.

**Two real bugs found only by running this, not by inspection:**

1. **Movement-legality gap**: `training/env_actions.py`'s legality check only ever verified board bounds (`apply_move` alone) — never `barriers.blocks(...)`, unlike every real caller (`CopBrain._pick_move` checks both). Before the fix, a cop could "move" onto its own placed barrier, and `legal_actions()` offered barrier-blocked directions as ordinary legal moves.
2. **Self-entrapment regression**: with barriers enabled, trained-policy reward genuinely *degraded* with more training against the real production config (first-half avg 10.62 -> last-half avg 7.09) — a correctness problem, not a cosmetic one, since it meant the resulting Q-table would be actively worse than no training at all. Root-caused by rolling out the fully-greedy trained policy: the cop placed barriers early and sometimes walled off its own last remaining exit, then STAY-looped for the rest of the episode to a `SURVIVAL` timeout instead of ever reaching the thief again — a failure mode `CopBrain`'s own heuristic avoids by construction (`_barrier_candidates` excludes its own preferred next step) but that nothing in the learned Q-table process shared. **Fix**: `legal_cop_actions` now excludes any barrier candidate that would seal the cop's own *last* open move, evaluated fresh against the live board every call — structurally guarantees the cop can never fully wall itself in, regardless of how many turns of accumulated barriers led up to it. Re-verified after the fix: first-half avg 11.05 -> last-half avg 13.04, reward climbing again.

A third, smaller finding: the existing `test_average_reward_in_the_second_half_beats_the_first_half` no longer converged reliably at its original 400-episode/2-stage-split design — the state/action space grew ~4-9x, and separately, once a third curriculum stage exists, its second-half window systematically faces a *harder* opponent, confounding "did it learn" with "did the opponent get harder" (a second, distinct instance of the curriculum-ordering trap this PRD already found once for the third stage itself). Fixed by raising `episode_count` to 2000, pinning the curriculum to a single stage for the test's own run, and comparing first/last-10% instead of halves — verified reliable across 8 seeds.

### Third curriculum stage

`lookahead_evader_thief` — depth-2 own-mobility lookahead. The `ThiefMover` interface structurally cannot see the cop's position (verified this rules out the plan's original "distance the cop could close" design), so this maximizes second-ply open-neighbour count instead; verified genuinely different from the existing 1-ply `greedy_escape_thief` via a 20,000-trial search (not just documentation-different), with a concrete disagreement case recorded in its own test.

### Reward-shaping documentation

No functional change — `training/reward.py`'s docstring now derives the exact Ng/Harada/Russell (1999) potential-based-shaping identity (`Φ(s) = -manhattan_distance`) and states plainly that the implementation omits the `γ` multiplier Ng's exact invariance guarantee calls for on `Φ(s')` — a documented approximation, not a hidden bug. Turned into a checked regression test, not just prose.

### Per-row quantization

PRD 12's per-table scheme scored 89.36% argmax-agreement (twice measured too low: 90.84%, 91.22% across PRD 12/13). `quantize_q_table_per_row` computes one `(scale, min_q)` pair *per state* instead of one shared by the whole table — same affine formula, finer grain. Real result on the same checkpoint: **100% argmax-agreement**, at a small, honest cost (`size_reduction_fraction=-0.054`, ~230KB vs. ~218KB unquantized — no longer smaller than the float original, a real trade-off).

**Found only by running it**: the first working version made the checkpoint 50% *larger* than unquantized (328KB) — a separate `"rows"` list re-serialized every state's key a second time, and Python's default float repr carried ~17 significant digits nothing here needs. Fixed by inlining each state's own rounded `(scale, min_q)` directly into its `q_values` entry instead (`rl_checkpoint_json.py`, split out of `rl_checkpoint_quant.py` once this landed, for the 150-line cap) — brought the overhead down to +5%. The size win is genuinely row-width-dependent, not universal: a realistic multi-action row still ends up smaller than float; a degenerate one-action-per-state table can legitimately end up ~1.2x larger — verified both directions, not assumed.

Backward compatibility: a `"mode"` key inside `"quantization"` distinguishes `"per_row"` from `"per_table"`, defaulting to `"per_table"` when absent — verified against a real hand-constructed file matching PRD-12/13's exact pre-existing shape (no `"mode"` key at all), not re-asserted from a docstring.

### Provenance

`training/pipeline/artifacts.py::write_provenance` records `git_commit_hash` (reusing `integrity/step0.py`), `hardware` (reusing `integrity/hardware_declaration.py`, `llm_model="none"` honestly — RL training never calls an LLM), the actual `RLTrainingConfig` used, and the game config's own path + SHA-256 — a new, run-scoped record, deliberately not `Step0Declaration` (whose fields are match-scoped, not training-run-scoped). Wired into `run_train`/`run_train_eval_cycle`.

## Rule-25-in-evaluate: rejected, documented only

The original proposal included automating a rule-25/I7 "compliance certificate" into `--stage evaluate`. **Rejected, no code written.** Rule 25/I7 compliance is a static property of `rl_cop_brain.py`'s code shape (every ranked action is re-checked live before use — see the Design table above), not a runtime metric a pipeline stage could measure. Automating it into `evaluate` would compete with, not strengthen, `.claude/agents/ml-promotion-gate.md`'s existing, deliberate design ("require, never re-derive a dated `rule-auditor` pass"), and risks the exact "auditor that quietly repairs symptoms and reports a clean bill of health" anti-pattern `rule-auditor.md` itself exists to prevent — a self-graded rubber stamp on exactly the layer where a bad policy could reach a real match. `rule-auditor` (human/agent-invoked, read-only, freshly dated) stays the sole source of truth for this rule.

## Explicitly out of scope

- **Opponent co-evolution** — not selected when the user was asked to scope the original proposal down; the third curriculum stage (a fixed, stronger heuristic) covers "make the opponent harder," not "make the opponent adapt to the trained policy."
- **Any Orchestrator/`cli_peer.py`/`config/game.toml` wiring** — the belief-confidence seam stays inert, matching the exact precedent `RLCopBrain` itself already set for two PRDs before PRD 13 touched deployment. No real match observes any of this PRD's changes.
- **Any new third-party dependency** — stayed tabular, stdlib-only, through all four ML PRDs (11-14).
- **Making a promotion commit** — unchanged from PRD 13's own explicit stopping point; nothing here creates `training/promoted/`.

## Also verify (acceptance criteria, checked once built)

- `legal_cop_actions` never offers a barrier placement that would leave the cop with zero legal moves (own dedicated test, plus a full `_decide_move` legality sweep over hundreds of randomized states).
- `SelfPlayEnv` matches `run_local_subgame` given the same policy and opponent, now including the real `barrier_quota` (not just the movement-only `barrier_quota=0` case PRD 11 already covered) — the one test that directly guards the rule-47 physics fix.
- A checkpoint's `state_encoding_version` and `quantization.mode` are both independently backward-compatible: a real `"v1"`, a real `"v2"`, and a real pre-per-row-mode `"quantization"` shape (no `"mode"` key) each still load or fail closed exactly as documented, verified against hand-constructed files matching those real historical shapes, not re-asserted from docstrings.
- `argmax_agreement_rate` genuinely measures something for per-row mode too, not a perpetual `1.0` by construction — a deliberately constructed within-row divergence (one dominant outlier value inside a single state's own row) still gets caught.

## New dependency

None. Every new/changed file (`training/belief_tracker.py`, `training/env_actions.py`, `rl_checkpoint_json.py`, the belief/barrier/quantization logic) is stdlib-only, reusing `src/cop/domain`/`src/cop/memory` primitives already in the repo — the "zero new dependency" story holds through all four ML PRDs.

## What's left (not part of this build pass, by design)

1. A human decision on whether/when to wire the belief-confidence seam or the barrier-decision path into a real match — both stay inert, matching PRD 11/13's own posture.
2. `ml-experiment-reporter`/`ml-promotion-gate` invocation against a PRD-14-era candidate checkpoint, if this layer's results are ever folded into a promotion decision — out of scope for this PRD, same stopping point PRD 13 already established.

## Builds on

PRD 11's `training/` package, `RLCopBrain`, and checkpoint format; PRD 12's quantization scheme (per-row coexists with, does not replace, per-table); PRD 13's pipeline stages and provenance-adjacent conventions. `src/cop/memory/{scent,belief}.py` (PRD 4) reused one-directionally inside training for the first time.
