# PRD 11 — RL Training Simulator & Tabular Q-Learning Brain

Status: **Done.** Built via `TODO11.md`, verified by `tests/unit/` (50 new tests, 100% coverage on every new module), a live run of `scripts/watch_prd11_rl_training.py`, and a `rule-auditor` pass scoped to rules 1/2/25/I2/I6/I7. `ruff check` clean. Full existing `tests/unit/` suite re-run in batches — zero regressions (three pre-existing, environment-specific real-HTTP-server hangs/failures confirmed identical on a clean `main` via `git stash`, not introduced here).

This is the deferred item `PRD-3-blind-strategy.md` explicitly named ("treat it as optional, later-if-time, not a PRD 3 deliverable") and PLAN.md §5's own PRD 3 text lists as "optionally Bellman/Q-learning" — picked up now with a full offline pipeline plan behind it (see the approved plan for PRD 12/13, the quantization and deployment layers this one is built to feed).

## Built & verified

The milestone — `RLCopBrain`, loaded from an offline checkpoint, beats a random-baseline mover against a seeded thief opponent over 20 episodes — is proven live by `scripts/watch_prd11_rl_training.py`: the default `config/rl_training.toml` (2000 episodes) trains in **0.50s** on the real `config/shared/config_dev_g01.json` board, reward climbs from a first-50-episode average of **13.83** to a last-50 average of **20.44** (approaching the Table 17 capture score of 20 plus shaping), and the trained brain reaches a **100% capture rate** against the random-walk baseline's **10%** over the same 20 seeded episodes.

**One real bug found via the parity test, not by inspection alone** — the same discipline `TODO1.md`/`TODO3.md` established: `SelfPlayEnv.step()`'s first draft checked `is_coordinate_capture` twice — once right after the cop's move, and again after the thief's move. That second check is physics-wrong: the game's actual capture rule (`domain/capture.py`) only ever fires on the cop landing on the thief, or a barrier on the thief's cell — never on the thief walking onto the cop. `tests/unit/test_training_env_parity.py` caught this immediately (`SelfPlayEnv` returned `CAPTURE` where `run_local_subgame`, given the identical policy and opponent, returned `SURVIVAL`). Fixed by moving the thief's move to only happen when the round didn't already end on the cop's own action, checking capture exactly once — matching `run_local_subgame`'s own order exactly. This is precisely why the parity test was built rather than trusted as an afterthought: `SelfPlayEnv` is a second, independent implementation of the same physics, and the two now provably agree.

## Build

- `src/cop/reasoning/rl_state_encoding.py` — `encode_state(own_pos, target_pos, board, barriers) -> (dx, dy, bitmask)`. Relative displacement, clamped to a **fixed** radius of 4 (not derived from `board.size` — see Design Question 1), plus a 4-bit "which orthogonal direction is blocked right now" mask.
- `src/cop/reasoning/rl_checkpoint.py` — `RLQTable` (read-only, inference-side), `save_checkpoint`/`load_checkpoint`. Canonical JSON (`sort_keys=True, separators=(",", ":")`), a `state_encoding_version` field checked on load, and a loud `ValueError` on anything malformed rather than a silently partial table.
- `src/cop/reasoning/rl_cop_brain.py` — `RLCopBrain(CopBrain)`, overrides only `_pick_move`. Table hit → ranked actions intersected with a Python-computed legal set (rule 25/I7: raw argmax is never trusted). Table miss, or no checkpoint at all → falls back to the inherited `CopBrain` heuristic.
- `training/` (new top-level package, one-directional dependency on `src/cop/`, enforced by `tests/unit/test_training_boundary.py`): `config.py` (`RLTrainingConfig`, loads `config/rl_training.toml`), `opponent_policies.py` (`make_random_walk_thief`, `greedy_escape_thief` — a deliberate duplication of `tests/support/greedy_thief_mover.py`, see Design Question 3), `reward.py` (`step_reward` — terminal reward reuses `GameConfig.score_capture_cop`/`score_survival_cop`, Table 17's real values, never reinvented), `q_table.py` (`QTable`, mutable, training-side), `env.py` (`SelfPlayEnv`, movement-only, no barriers — see Design Question 2), `train_loop.py` (`train()`, epsilon-greedy with a two-stage curriculum), `checkpoint_io.py` (the training-side wrapper into `rl_checkpoint.py`).
- `config/rl_training.toml` — RL-only tunables, explicitly never Appendix F territory (see the file's own header comment).
- `pyproject.toml` — `training` added alongside `src/cop` in `[tool.hatch.build.targets.wheel] packages`, so `import training` resolves the same way `import cop` already does.
- `scripts/watch_prd11_rl_training.py` — the milestone demo.

## Explicitly out of scope

- Any wiring into `Orchestrator`, `cli_peer.py`, or `config/game.toml`'s `police_class` — PRD 13's job entirely. `RLCopBrain` is fully built and tested here but not referenced from anywhere a real match would run.
- Barrier-placement RL. `RLCopBrain` overrides only `_pick_move`; `_decide_move`'s barrier heuristic is inherited unchanged from `CopBrain`. `SelfPlayEnv` never places a barrier during training (see Design Question 2) — barrier RL is a real, separate problem, named here as later-if-time, exactly the posture `PRD-3-blind-strategy.md` already took toward RL itself.
- Quantization (PRD 12) and any deployment/promotion machinery (PRD 13).
- A neural network, function approximation, or a `torch`/`numpy` dependency — the state space (~2,401 relative-displacement states × 4-bit barrier mask, well within a tabular table's reach) doesn't need one; see the approved plan's fork note for what would change if it did.
- Multi-agent joint training — the synthetic opponent is a fixed-policy curriculum stage per episode, never co-trained with the cop.

## Rules owned

No rule in Appendix E is newly triggered by an offline, sandbox-only training layer — training happens entirely between games, off the graded critical path (matches `PLAN.md` §6's own framing). What this layer re-verifies, in a new code shape, for the first time:

| Invariant | How this layer satisfies it |
|---|---|
| I1/I2 (rules 1, 2) | The synthetic sparring opponents are plain functions, never a `BrainBase`/`ThiefBrain` subclass, and structurally unreachable from `src/cop/` — `test_training_boundary.py` makes that a regression-tested fact, not a documented convention. |
| I7 (rule 25) | `RLCopBrain._pick_move` returns a legality-masked, deterministic string; the raw Q-table ranking never reaches a caller unfiltered. |
| I6 | Every *game* magnitude (`board.size`, `barriers.quota`) the encoding touches comes from the `Board`/`BarrierSet` objects already passed into `_pick_move` — nothing hardcoded from memory. RL hyperparameters live in their own `config/rl_training.toml`, explicitly not Appendix F territory (same precedent `PARAMETERS.md`'s own closing section already sets for `belief.py`'s `_HINT_RELIABILITY`). |

## Milestone

`scripts/watch_prd11_rl_training.py` trains offline (2000 episodes, 0.50s), saves a checkpoint, loads it into a fresh `RLCopBrain`, and evaluates it against a random-move baseline cop over 20 seeded episodes of a random-walk thief — both run through `reasoning/subgame.py::run_local_subgame`, no `Orchestrator`, no network. `RLCopBrain` reaches a measurably higher capture rate (100% vs. 10% in the run recorded above) — watched directly, not asserted from a log.

## Design questions answered here (not left for code-time guessing)

**1. Should the state-encoding clamp radius scale with `board.size`?** No — fixed at 4, deliberately independent of board size. The approved plan's own text originally suggested deriving it from `board.size`, but building the encoder surfaced the actual tradeoff: a board-size-scaled radius would let the table's size grow unbounded as `board.size` is raised (Table 13's `grid_size` is a MINIMUM, negotiable upward per rule 12), defeating the point of a compact, generalizing key. A fixed radius keeps every state beyond it folding into the same "far, just close the gap" bucket — still correctly biased toward pursuit, and the table's size stays bounded regardless of how large the board gets. Corrected during the build, not assumed at design time — the same category of correction `PRD-3`'s own retrospective already documents as normal, not something to hide.

**2. Why does `SelfPlayEnv` never place a barrier, even though `run_local_subgame` and `CopBrain._decide_move` both support it?** Because `RLCopBrain` only ever learns `_pick_move` (Design Question in "Explicitly out of scope" above) — training a movement-only policy against a movement-only environment keeps the state space clean and the training loop simple. The real consequence, worth stating plainly: **any state with a real barrier adjacent to the cop is guaranteed to miss the trained table** (its bitmask bits were never populated during training), so `RLCopBrain` falls back to the inherited `CopBrain` heuristic in exactly those states — `tests/unit/test_rl_cop_brain.py::test_a_barrier_adjacent_state_is_never_in_a_training_produced_table_and_falls_back` makes this explicit and checked, not just implied. This is a deliberate, honest scope boundary, not an oversight: barrier interaction is exactly the kind of longer-horizon planning problem tabular Q-learning over this compact a state space isn't attempting to solve in v1.

**3. Why duplicate `tests/support/greedy_thief_mover.py`'s algorithm into `training/opponent_policies.py` instead of importing it?** Two reasons, both already established precedent in this repo (PRD-3's own Design Question 5 made the same call for the same reason): (a) `tests/` is test scaffolding, not a stable internal API — a test refactor could silently change training behaviour if training depended on it; (b) it keeps "`training/` never imports from `tests/`" exactly as unambiguous as "`training/` never imports from `src/cop/`" — one clean rule, not an exception carved out for convenience. The duplication is ~20 lines.

**4. Why is `SelfPlayEnv` a second implementation of the turn loop instead of reusing `run_local_subgame` directly?** Epsilon-greedy training must choose the movement action itself, with exploration noise — `run_local_subgame` delegates that choice entirely to `cop_brain._decide_move`, an already-fixed policy, with no seam to inject the action being learned. Reimplementing the same physics shape and then *proving* the two agree (`test_training_env_parity.py`, and the real bug that test caught — see "Built & verified" above) is the honest way to get both properties: an environment training can drive, and confidence it isn't quietly diverging from the one game engine that actually matters.

**5. Why does a missing/corrupted checkpoint make `RLCopBrain` behave exactly like `CopBrain` instead of raising?** Because that's the correct, safe state for every point in this project's lifecycle *before* a checkpoint has been trained and promoted (PRD 13) — including right now, since PRD 11 builds `RLCopBrain` but wires nothing. Raising would make the class impossible to construct or test until PRD 13 exists; falling back is also the same "never worse than baseline" property Design Question 2 already relies on for the table-miss case, applied consistently to the whole-checkpoint-missing case too.

## Also verify (acceptance criteria, checked once built)

- `RLCopBrain._pick_move`'s output is always legal — proven over 500 randomized states, with and without a populated checkpoint, mirroring `test_cop_brain_legality_sweep.py`'s existing pattern (`test_rl_cop_brain.py`).
- A Q-table entry that ranks only illegal actions still falls back to `"STAY"`, never an out-of-bounds or barrier-blocked move.
- `SelfPlayEnv` and `run_local_subgame` reach the identical `Outcome` given the same fixed policy and opponent — regression-tested, not assumed (`test_training_env_parity.py`).
- The same training seed produces an identical trained table and reward history; a different seed produces a different one (`test_train_loop.py`).
- Nothing under `src/cop/` imports `training/` — checked structurally, and the check itself is proven to catch a real violation, not just pass by construction (`test_training_boundary.py`).
- No new magic numbers: RL hyperparameters come from `config/rl_training.toml`/`RLTrainingConfig`, never a hardcoded literal inside `training/` or `src/cop/reasoning/rl_*`.

## New dependency

None. `training/` and the new `src/cop/reasoning/rl_*` files are pure standard-library Python (`random`, `json`, `dataclasses`, `tomllib` — the same stdlib TOML reader `private_config.py` already uses). This is a literal instance of Ch. 5.5's computational-fairness framing, not just a citation of it: no `torch`, no `numpy`, no GPU, training a full 2000-episode run in well under a second on ordinary hardware.

## Builds on

PRD 1's `domain/` (board, movement, barriers, capture, end_conditions) and PRD 3's `reasoning/brain_base.py`/`cop_brain.py`/`subgame.py` are reused as-is — `RLCopBrain` subclasses `CopBrain` rather than reimplementing `BrainBase`, and `run_local_subgame` is the parity oracle `SelfPlayEnv` is checked against, not replaced.
