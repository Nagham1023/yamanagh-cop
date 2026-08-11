# TODO11 — Build Checklist for PRD 11 (RL Training Simulator & Tabular Q-Learning Brain)

Status: **Done.** Read `PRD/PRD-11-rl-training-simulator.md` in full first — its Design Questions section documents two decisions corrected *during* this build (the clamp radius, and the double-capture-check bug the parity test caught), not anticipated at design time.

## 1. `src/cop/reasoning/rl_state_encoding.py` — the Q-table key

- [x] `encode_state(own_pos, target_pos, board, barriers) -> (dx, dy, bitmask)` — relative displacement clamped to a fixed radius (4), plus a 4-bit "blocked right now" mask per orthogonal direction.
- [x] Test: relative displacement, not absolute position (two different absolute positions with the same offset encode identically).
- [x] Test: displacement beyond the clamp radius saturates.
- [x] Test: negative displacement preserves sign.
- [x] Test: off-board neighbours set bitmask bits; a fully-open center cell encodes bitmask 0.
- [x] Test: a real barrier sets a bitmask bit a pure board-edge state wouldn't have (the property `RLCopBrain`'s fallback safety depends on).
- [x] Test: deterministic for the same inputs.

## 2. `src/cop/reasoning/rl_checkpoint.py` — canonical checkpoint format

- [x] `RLQTable` (read-only, inference-side) with `ranked_actions(state) -> list[str] | None`.
- [x] `save_checkpoint`/`load_checkpoint` — canonical JSON (`sort_keys=True, separators=(",", ":")`), `state_encoding_version` field checked on load.
- [x] Rejection test: missing file raises `FileNotFoundError`.
- [x] Rejection test: not valid JSON raises `ValueError`.
- [x] Rejection test: missing required keys raises `ValueError`.
- [x] Rejection test: an unrecognized `state_encoding_version` raises `ValueError`.
- [x] Test: save/load round-trips ranked actions correctly; an unvisited state returns `None`, not an empty list.

## 3. `src/cop/reasoning/rl_cop_brain.py` — the production brain

- [x] `RLCopBrain(CopBrain)`, overrides only `_pick_move`. `_decide_move`'s barrier heuristic is inherited unchanged.
- [x] Q-table hit: ranked actions intersected with a Python-computed legal set before returning — raw argmax never trusted directly (rule 25/I7).
- [x] Q-table miss, or missing/corrupted checkpoint at construction: falls back to the inherited `CopBrain` heuristic, never a guess or a crash.
- [x] Rejection/property test: 500 randomized states, with and without a populated checkpoint — output always legal, mirroring `test_cop_brain_legality_sweep.py`'s existing pattern.
- [x] Test: a table entry ranking only illegal actions falls back to `STAY`.
- [x] Test: a barrier-adjacent state is never present in a training-produced table and falls back correctly.

## 4. `training/` — the offline simulator (sandbox-only, one-directional dependency on `src/cop/`)

- [x] `config.py` — `RLTrainingConfig.from_toml`/`from_dict`, reads `config/rl_training.toml`. Test: reads every section; missing section raises `KeyError`.
- [x] `opponent_policies.py` — `make_random_walk_thief` (seeded closure), `greedy_escape_thief` (deliberate duplication of `tests/support/greedy_thief_mover.py`, see PRD's Design Question 3). Tests: both always legal, deterministic for a seeded rng, stay when boxed in; `greedy_escape_thief` provably prefers the neighbour with more open escape routes.
- [x] `reward.py` — `step_reward`: terminal reward reuses `GameConfig.score_capture_cop`/`score_survival_cop` (Table 17, never reinvented); in-progress steps get RL-only distance-shaping minus a step cost. Tests: capture/survival/technical-loss/in-progress branches, both distance-closing and distance-opening shaping signs.
- [x] `q_table.py` — `QTable`, mutable, training-side. Tests: value/update round-trip, `best_value`, `best_legal_action` ignores illegal actions even when they'd score higher, `as_dict` is a plain dict.
- [x] `env.py` — `SelfPlayEnv`, movement-only (no barrier placement — see PRD's Design Question 2). **Found only by actually running the parity test**: the first draft double-checked capture (once after the cop's move, once after the thief's) — physics-wrong, since the thief walking onto the cop is never itself a capture. Fixed to check exactly once, matching `run_local_subgame`'s order.
- [x] `train_loop.py` — `train()`, epsilon-greedy, two-stage curriculum (`random_walk_thief` before `curriculum_switch_episode`, `greedy_escape_thief` after). Tests: same seed → identical trained table; different seed → different table; `episode_count`/epsilon-floor respected; average reward in the second half of training measurably beats the first half (the actual learning-signal proof, not just "runs without crashing").
- [x] `checkpoint_io.py` — thin `save()` wrapper into `rl_checkpoint.py`. Tests: round-trips through the production loader; an empty table produces a loadable, all-miss checkpoint.
- [x] `test_training_env_parity.py` — `SelfPlayEnv` reproduces `run_local_subgame`'s outcome given the identical fixed movement policy and opponent (this is the test that caught the bug above).
- [x] `test_training_boundary.py` — grep-based structural check that nothing under `src/cop/` imports `training/`; a second test proves the check pattern itself actually catches a synthetic violation, not just passes by construction.

## 5. Packaging

- [x] `pyproject.toml`: `training` added to `[tool.hatch.build.targets.wheel] packages`, alongside the existing `src/cop` — `import training` now resolves the same way `import cop` already does, in scripts and tests alike. `uv sync` re-run to confirm the editable install picked it up.

## 6. `config/rl_training.toml`

- [x] Written with a header comment stating explicitly: RL-only tunables, never Appendix F, never checked by `check_config.py`, never part of the byte-identical config comparison (rule 11) — same status precedent `PARAMETERS.md`'s own closing section already sets for `belief.py`'s `_HINT_RELIABILITY`.

## 7. `scripts/watch_prd11_rl_training.py`

- [x] Trains the real default `config/rl_training.toml` against the real `config/shared/config_dev_g01.json` board, saves a checkpoint, loads it into a fresh `RLCopBrain`, and evaluates capture rate against a demo-only random-baseline brain over 20 seeded episodes of a random-walk thief.
- [x] Run and watched: 2000 episodes trained in 0.50s, reward climbed from a first-50-episode average of 13.83 to a last-50 average of 20.44, `RLCopBrain` reached a 100% capture rate vs. the random baseline's 10% over the same 20 episodes.

## Cleanup and final verification

- [x] Every new file checked against the 150-line house cap (largest is `training/env.py` at 116 lines) and carries a module/class/function docstring.
- [x] `uv run ruff check` on every new file — clean (three trivial unused-import/import-order/`dict()`-literal issues auto-fixed during the build, not left in).
- [x] `uv run pytest` on the new PRD-11 suite alone: 50 passed, 100% coverage on every new module (`training/*`, `src/cop/reasoning/rl_*`).
- [x] Full existing `tests/unit/` suite re-run in two batches (this repo's own documented "split into batches" precedent, `TODO9.md`) — zero regressions. Three failures/hangs encountered (`test_cost.py`'s one token-logging test, `test_orchestrator_take_turn.py`'s belief/scent test, `test_step_index_agreement.py`) were each individually confirmed to fail/hang identically on a clean `main` via `git stash` before this layer's changes — pre-existing, environment-specific real-HTTP-server flakiness in this sandbox, not introduced here.
- [x] `git log --all --full-history -- '*credentials*' '*token.json*' '*.env'` — still empty.
- [x] `rule-auditor` pass scoped to rules 1/2/25/I2/I6/I7 and the new files — see `PRD/PRD-11-rl-training-simulator.md`'s Status line for the result.
- [x] `TODO.md`'s own master checklist — PRD 11 row added.
- [x] `PRD/PRD-11-rl-training-simulator.md` written, built, and verified against this checklist; commit.
