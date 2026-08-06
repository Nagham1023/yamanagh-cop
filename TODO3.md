# TODO3 — Build Checklist for PRD 3 (Blind Strategy)

Status: **Done.** Built, tested (128 tests + 1 xfailed, 100% coverage), `ruff` clean, `check_config.py` 31/31, `rule-auditor`-clean, milestone watched running live. Mirrors `PRD-3-blind-strategy.md`'s scope and its five Design Questions; each item is independently actionable (file + what "done" looks like), same specificity level as `TODO2.md`.

**Two real bugs found and fixed during §8/§10** (not anticipated by this checklist, found via actually running the milestone): (1) the barrier heuristic could block the cop's own best path, causing a permanent movement oscillation — fixed in §4/§3's `CopBrain._decide_move` by excluding the cop's own preferred next step from barrier candidates; (2) the original self-trap check became provably-dead code once (1) was fixed, and was removed rather than kept untested. See `PRD-3-blind-strategy.md`'s "Built & verified" section for the full account.

## 0. Setup

- [x] Confirm no new `GameConfig` fields are needed — `board_size`, `barrier_quota`, `step_ceiling`, `cop_start`, `thief_start` already exist from PRD 1. Only add a field if a barrier-placement heuristic genuinely needs a tunable threshold (I6); do not add one speculatively.
- [x] `src/cop/reasoning/__init__.py` — module docstring only

## 1. `BrainBase` contract (`src/cop/reasoning/brain_base.py`)

- [x] Abstract base class with `_pick_move(own_pos, target_pos, board, barriers) -> str` (abstract; returns one of `movement.DELTAS`' keys) and `_decide_move(own_pos, target_pos, board, barriers) -> Action` (concrete default: wraps `_pick_move`'s result in a `Move` action — subclasses override only what they need to change).
- [x] Define the `Action` result type (e.g. a small tagged union / two frozen dataclasses: `Move(direction: str)`, `PlaceBarrier(target: Position)`) — this is what `_decide_move` returns and what `Orchestrator.take_turn()` consumes.
- [x] Docstring: state explicitly that this is *not* the book reference repo's `BrainBase`/`ThiefBrain` hierarchy — ours is scoped to what this repo actually needs (Design Question 5), and a mismatch with the reference repo's class names is not a bug.
- [x] Unit test: `BrainBase`'s default `_decide_move` calls `_pick_move` and wraps it in `Move` — verified with a minimal concrete subclass that only implements `_pick_move`.
- [x] Rejection test: `BrainBase` itself cannot be instantiated directly (ABC enforcement) — attempting it raises `TypeError`.

## 2. Per-turn state (`src/cop/reasoning/state.py`)

- [x] `GameState` (or similar) dataclass: `own_pos: Position`, `target_pos: Position`, `barriers: BarrierSet`, `steps_taken: int`. Mutable where it needs to be (position and step count change every turn) — not frozen, unlike `Board`/`Position`.
- [x] A method or free function to advance state by one applied `Action`: for `Move`, delegate the destination computation to `domain.movement.apply_move(own_pos, direction, board)` (bounds check included) rather than reimplementing position arithmetic; for `PlaceBarrier`, add to `barriers` and leave `own_pos` unchanged (the forgo-move rule, enforced here).
- [x] Docstring: explicit that `target_pos` is ground truth for this layer (Design Question 4) and PRD 4 changes *where this value comes from*, not this class's shape.
- [x] Unit test: applying a `Move` action updates `own_pos` and increments `steps_taken`; applying a `PlaceBarrier` action updates `barriers` and does **not** move `own_pos` (the forgo-move rule, tested directly).
- [x] Rejection test: applying a `PlaceBarrier` action when `barriers.can_place(...)` is false does not silently no-op into a move, and does not corrupt state — decide and test the actual failure shape (raise, or return an unchanged state — pick one, document why).

## 3. `CopBrain` — movement heuristic (`src/cop/reasoning/cop_brain.py`)

- [x] `CopBrain(BrainBase)`. `_pick_move` implements greedy Manhattan-distance descent: among the four orthogonal `DELTAS` (excluding `STAY` unless no other legal option exists), pick the destination that minimizes `|dst.col - target.col| + |dst.row - target.row|` among those that pass **both** `domain.movement.apply_move(own_pos, direction, board) is not None` (bounds) **and** `not barriers.blocks(destination)` (not barrier-occupied) — reuse both functions, don't reimplement the checks.
- [x] Deterministic tie-break for equal-distance candidates (fixed direction priority order, e.g. N, E, S, W) — document the order in the docstring so behaviour is reproducible and testable, not "whatever dict iteration order happens to be."
- [x] `STAY` is only chosen when every orthogonal move is illegal or off-board (mirrors `capture.thief_has_no_legal_move`'s treatment of `STAY`).
- [x] Unit test: given a target directly N/S/E/W of the cop, `_pick_move` returns the direction that closes the distance.
- [x] Unit test: given a target on the diagonal, `_pick_move` returns one of the two tie-broken legal options deterministically (same input twice, same output).
- [x] Rejection test: a target beyond a barrier-blocked cell in the "obviously shortest" direction — `_pick_move` must not propose a move into a blocked cell just because it looks shortest; confirm it picks the next-best legal option instead.
- [x] Rejection test: cop in a corner with the target off-board in the naive direction — `_pick_move` never proposes an off-board destination (backstopped by `domain/`, but the brain shouldn't be relying on that backstop to avoid an obviously bad choice).

## 4. `CopBrain` — barrier policy (`_decide_move`)

- [x] `CopBrain` overrides `_decide_move`: decide whether to forgo movement and place a barrier this turn instead of calling `_pick_move`. Simplest defensible heuristic, stated plainly in code comments: place a barrier only when doing so is adjacent to the cop's current cell (rule: only own-cell or one-cell-adjacent, from `BarrierSet.can_place`) **and** meaningfully restricts the target's escape routes **and** does not reduce the cop's own count of legal orthogonal moves to zero. **Changed during build:** the "does not trap the cop" condition originally planned as an explicit reuse of `domain.capture.thief_has_no_legal_move(own_pos, board, barriers_after_hypothetical_placement)` was replaced — a real bug (the barrier heuristic blocking the cop's own best path, causing a permanent oscillation) led to also excluding the cop's own preferred next step from barrier candidates, which turned out to structurally subsume the self-trap check entirely (proven unreachable by coverage analysis, then removed as dead code). See `PRD-3-blind-strategy.md`'s "Built & verified" section.
- [x] No new hardcoded thresholds — if "meaningfully restricts" needs a numeric cutoff, it must come from `GameConfig`, not a bare literal in `cop_brain.py` (I6, game-rule quantities only — this does not extend to internal tie-break/heuristic-shape constants, see PRD Design Question 1's note). If the heuristic can be expressed without a new tunable number (e.g. "only if it's one of the target's currently-open neighbours"), prefer that over inventing a config field.
- [x] Unit test: given quota remaining and a barrier placement adjacent to the cop that would not trap the cop, `_decide_move` returns `PlaceBarrier`, not `Move`.
- [x] Unit test: given quota exhausted (`BarrierSet.quota` already met), `_decide_move` always returns `Move` — never attempts an over-quota placement.
- [x] Rejection test (the "also verify" line from the PRD, made concrete): construct a position where the *only* available barrier placement would reduce the cop's own legal-move count to zero — `_decide_move` must not choose it; confirm it falls back to `Move` instead.
- [x] Rejection test: a barrier placement that would land on the cop's own current cell in a way that's legal per `BarrierSet` but pointless (does not restrict the target at all) — confirm the heuristic doesn't burn quota for no reason. **Satisfied structurally, no dedicated test needed:** `_barrier_candidates` only ever generates the cop's 4 orthogonal neighbours, never its own cell (documented in `cop_brain.py`) — the scenario this item worried about can't occur by construction, which is stronger than a runtime check. `test_decide_move_falls_back_to_move_when_no_placement_restricts_the_target` covers the general "nothing useful to place" case.

## 5. Thief test fixture (`tests/support/greedy_thief_mover.py`)

- [x] A plain function, **not** a `BrainBase` subclass, **not** under `src/cop/` — `greedy_thief_move(own_pos, board, barriers) -> str`, returning the `DELTAS` key whose destination has the most open orthogonal neighbours (ties broken deterministically, same style as `CopBrain`). Reuse `board.in_bounds` + `barriers.blocks()` for the neighbour scan — don't reimplement it.
- [x] Module docstring states explicitly why this exists and why it is not a `ThiefBrain`: Design Question 5 — `thief_class` is the teammate's own repo's concern (Table 22), this is local test/demo scaffolding only, never imported by `orchestrator.py` or anything under `src/cop/`.
- [x] Unit test: given a cell with more open neighbours to one side than the other, the fixture prefers the side with more escape routes.
- [x] `rule-auditor` check (fold into §10): confirm nothing under `src/cop/` imports from `tests/support/` — that import direction would be the actual rule-1 violation risk, not the fixture's mere existence.

## 6. State machine: `COMPUTING_MOVE`

Given the local/network split in §7–8, `COMPUTING_MOVE` is only ever exercised by `take_turn()`'s own test — trim accordingly, don't over-test a state with one caller.

- [x] Extend `planner/state_machine.py`'s `TRANSITIONS` table: `WAITING_FOR_OPPONENT → COMPUTING_MOVE → SENDING → AWAITING_RESPONSE → TURN_RESOLVED → WAITING_FOR_OPPONENT`, `TECHNICAL_LOSS` reachable from every state including the new one. Add `COMPUTING_MOVE` to the existing parametrized "every non-terminal state can reach `TECHNICAL_LOSS`" test's parameter list — don't write a new test for it.
- [x] Docstring update (same pattern as the existing note about PRD 6's `COMMITTING`/`AWAITING_REVEAL`): record that `COMPUTING_MOVE` is now real, not a future placeholder.
- [x] Unit test: `WAITING_FOR_OPPONENT → COMPUTING_MOVE → SENDING → AWAITING_RESPONSE → TURN_RESOLVED → WAITING_FOR_OPPONENT` succeeds as a full cycle (extend the existing `test_full_round_trip_cycle_is_legal`-style test, don't fork a parallel one).
- [x] Rejection test: `WAITING_FOR_OPPONENT → SENDING` directly (skipping `COMPUTING_MOVE`) is now illegal — confirm the old PRD 2 shortcut is correctly rejected under the new table.

## 7. Orchestrator wiring — the wiring proof only (`orchestrator.py`)

Deliberately kept small: this proves `CopBrain` is genuinely reachable through `Orchestrator`, not that the algorithm works — algorithm correctness is §8's job, entirely offline. See PRD Design Question 3.

- [x] `Orchestrator.__init__` gains a `brain: BrainBase` constructor argument.
- [x] `Orchestrator.take_turn(peer_url: str) -> dict`: transitions to `COMPUTING_MOVE`, asks `self.brain._decide_move(...)` using current `reasoning/state.py` state, applies the resulting `Action` to local state, then calls the existing `send_to_peer` (which still owns `SENDING → AWAITING_RESPONSE → TURN_RESOLVED`/`TECHNICAL_LOSS`) with the resulting `(col, row)`. One turn only — no internal loop, no `determine_outcome` call here.
- [x] Watch the 150-line house cap — `orchestrator.py` is already at ~106 lines before this task. `take_turn()` staying single-turn (not housing a full loop) should keep this manageable; if it still pushes over, split by extracting the turn-taking logic into its own module rather than letting the cap slide.
- [x] Unit test (the "wiring is real" test from the PRD's "Also verify"): a test that would fail if `take_turn()` silently ignored `self.brain` and sent a fixed position instead — e.g. two brains with different, known target positions produce two different, correctly-different outgoing `(col, row)` values reaching a live peer.
- [x] Rejection test: calling `take_turn()` from an illegal starting state raises via the state machine, same as the existing `send_to_peer` illegal-transition coverage — don't let the new method bypass rule 5's enforcement.

## 8. Local turn loop — the milestone (`src/cop/reasoning/subgame.py`)

Pure Python, no `Orchestrator`, no network, no subprocess — calls `CopBrain`/`greedy_thief_move`/`domain/` functions directly. This is what the milestone and every multi-turn/convergence test run against, so a failure here is isolated to a `reasoning/`+`domain/` bug, never a networking one. See PRD Design Question 3.

- [x] `run_local_subgame(cop_brain, thief_mover, board, config) -> Outcome`: repeatedly calls `cop_brain._decide_move(...)`, applies the result via `reasoning/state.py`, advances the thief side via `thief_mover` (or holds it fixed for the static-target case), checks capture via `domain/capture.py`, and calls `domain/end_conditions.determine_outcome` every turn — stopping the instant it returns a non-`None` `Outcome`.
- [x] Fix `end_conditions.py`'s stale docstring ("PRD 2's turn loop will call `determine_outcome`") — PRD 2 never built a turn loop; `run_local_subgame` is the first thing that actually does. Update the comment to say so accurately.
- [x] Test: a static known target — `CopBrain` reaches (or captures) it within a bounded number of turns, well under `step_ceiling`, with `determine_outcome` returning `Outcome.CAPTURE` at the right moment (the core milestone, made concrete).
- [x] Test: the greedy-thief fixture, moving every turn — **changed during build:** empirically, the distance sequence against the fixture is *not* monotonically non-increasing (measured trace: `[6, 4, 2, 3, 3, 3, 1]` before capture) — the escape-route heuristic isn't distance-aware, so a "non-increasing window" assertion would have been false. The honest, still-meaningful claim used instead: `run_local_subgame` reaches `Outcome.CAPTURE` against the actively-evading fixture, proving genuine pursuit success, not just a first-move coincidence.
- [x] Test: force a scenario that never captures within `step_ceiling` (e.g. a board/start position engineered so the thief always has an escape) — confirm the loop stops at `step_ceiling` with `Outcome.SURVIVAL`, not an infinite loop and not a silent early exit.
- [x] Rejection test: `determine_outcome` is checked and respected even on the exact turn the ceiling is reached simultaneously with a capture — capture wins (already covered by `domain/end_conditions.py`'s own unit tests from PRD 1; add one test here that exercises it through `run_local_subgame`, not just the pure function).

## 9. Live demo script (`scripts/watch_prd3_brain.py`)

Two clearly-labeled sections, matching the §7/§8 split — don't blur them into one undifferentiated run.

- [x] Section 1 — local pursuit, no subprocess: run `run_local_subgame` against both the static-target and moving-fixture-thief scenarios, printing each turn's chosen action and the resulting distance-to-target.
- [x] Section 2 — one real round-trip: spin up one real peer process (reusing `tests/integration/_server_process.py`, unmodified — it only needs to keep acking positions, it doesn't need a brain), call `Orchestrator.take_turn()` once, print the `COMPUTING_MOVE` transition and the resulting `(col, row)` that reached the peer, proving the wiring live.
- [x] Exact terminal run command documented in the script's own docstring and added to `TODO.md`'s "Demo scripts" block, same as PRD 1/2's scripts.

## 10. Wrap-up

- [x] `uv run pytest` — full suite green, coverage ≥85% on all new code (aim for the 100% this repo has held since PRD 1)
- [x] `uv run ruff check .` — clean
- [x] `check_config.py` — still 31/31 (confirm whether §0's "no new fields" decision held; update this item if a field was added after all)
- [x] File line counts: every new/touched file under the 150-line house cap — `orchestrator.py` *did* go over (162 lines) once the own critical pass's exception-handling fix landed; split `take_turn()` into `orchestrator_turn.py`'s `BrainTurnMixin` (123 + 53 lines)
- [x] `rule-auditor` run against rule 25, invariant I7, and specifically Design Question 5's rule-1 boundary (confirm nothing under `src/cop/` imports `tests/support/greedy_thief_mover.py`) — clean, zero fatal/non-fatal violations (rules 1–5, 25, I2, I7)
- [x] Watch `scripts/watch_prd3_brain.py` run live, end to end, by a human — re-run again after the mixin split, still clean
- [x] Sanity-check the milestone claim the way the PRD 2 concurrency claim was checked: temporarily break the Manhattan heuristic (e.g. make `_pick_move` always return a fixed direction) and confirm the milestone test actually fails — if it still passes, the test isn't proving what it claims to. Then revert. Confirmed: sabotaged to always `"STAY"`, milestone test failed with `Outcome.SURVIVAL` instead of `Outcome.CAPTURE`, reverted, re-read to confirm.
- [x] Update `PRD/PRD-3-blind-strategy.md` — flip status to Done, add a retrospective "Built & verified" section (same shape as PRD 1 and PRD 2's)
- [x] Update `TODO.md` — PRD 3 row to done, demo script command added
- [x] Own critical pass, `TODO1.md`/`TODO2.md`-style but retrospective — found a third real gap: `take_turn()` didn't catch exceptions from the brain/`GameState.apply`, unlike `send_to_peer`'s own careful handling; fixed with the same catch-log-transition-reraise shape, regression test added
- [x] Commit — `65074f9`
