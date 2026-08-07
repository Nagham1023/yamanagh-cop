# TODO1 — Critical Review of PRD 1 (Base Logic)

This is not a status list. `TODO.md` already tracks PRD 1 as done, and `PRD/PRD-1-base-logic.md` documents what was built. This file's only job is to interrogate that verdict — look for what the automated checks (44 passing tests, 100% coverage, `ruff` clean, `check_config.py` 31/31, `rule-auditor` zero-fatal) didn't catch, because they only catch what they were written to catch.

## Verdict

**Update: all five findings below are now fixed.** This review originally found one reproducible behavioural bug and three real gaps the standard audit missed — none were rule violations, but "no fatal rule violation" and "correct" are not the same claim, and PRD 1's milestone bar (CLAUDE.md: watched, tested, audited) implicitly promises the second one too. Each finding below is kept as-written (the bug report, not a sanitized after-the-fact description) with a "Fixed" line appended, so the record of what was actually wrong survives the fix. Test count went from 44 → 52; `ruff`/`check_config.py`/the live demo (`scripts/watch_prd1.py`) were all re-run clean afterward.

## 1. Real bug — a barrier off the board silently consumes quota

Reproduced directly, not hypothesized:

```
cop = Position(0, 0)            # corner
target = Position(-1, 0)        # off-board, manhattan distance 1 from cop
board.in_bounds(target)         # False — correctly off-board
barriers.can_place(cop, target) # True  — accepted anyway
barriers.place(cop, target)     # True  — placed
# quota consumed: 1 / 14, for a barrier that can never block or capture anything
```

`BarrierSet.can_place` was deliberately written to skip bounds-checking ("the caller's job" — see the docstring), on the theory that PRD 1 has no caller yet so it's a documented deferral, not a live bug. That reasoning is wrong: the *method* is fully reachable and fully tested-as-if-complete today, and nothing currently stops it from being called directly with a bad target. A cop brain in PRD 3 that computes a target near a corner and gets its own math wrong would burn one of its 14 barriers for nothing, silently, with no error — exactly the kind of invisible failure this whole project is designed to guard against elsewhere (spec-guard's own thesis).

- [x] Fix: `BarrierSet.can_place`/`place` must take a `Board` and reject out-of-bounds targets, matching `movement.apply_move`'s existing symmetry with `board.in_bounds`.
- [x] Add regression test: barrier at an off-board cell adjacent to a corner cop is rejected and does not consume quota (`test_barrier_off_the_board_edge_is_rejected`).

**Fixed.** `barriers.py` now takes `board: Board` in both `can_place` and `place`; every call site (tests, `scripts/watch_prd1.py`) updated.

## 2. Untested — config values are never proven to drive behaviour end-to-end

`rule-auditor` marked invariant I6 CLEAN because no module hardcodes a board size, quota, or score literal — that's a *structural* check. No test anywhere loads `GameConfig` and then proves changing a config value actually changes domain behaviour. `test_barriers.py` constructs `BarrierSet(quota=2)` directly; `test_board.py` constructs `Board(size=7)` directly. If someone edits `config_dev_g01.json`'s `movement_and_barriers.max_barriers` to `5` tomorrow, nothing in the test suite would fail if the code silently ignored it and kept using some other number — because no test exercises that pipeline.

- [x] Add one integration test: `GameConfig.from_file(...)` → `BarrierSet(quota=config.barrier_quota)` → confirm the *loaded* value, not a hardcoded one, gates the quota rejection.
- [x] Same for `Board(size=config.board_size)`.

**Fixed.** `tests/unit/test_config_wiring.py` — two tests, both loading a real `GameConfig` and proving the loaded value (not a literal) drives `Board`/`BarrierSet` behaviour.

## 3. Latent correctness risk — `origin`/`index_base` are loaded but never consulted

`GameConfig` parses `origin` ("top-left") and `index_base` (`0`) from the config file — both **NEGOTIABLE** per Table 13, meaning either side could legally propose different values. `Position`/`Board` hardcode the top-left/index-0 assumption in a comment, not in logic that reads `config.origin`/`config.index_base`. Today this matches the default, so nothing is visibly wrong. The moment a negotiated game ever sets `origin: "bottom-left"` or `index_base: 1`, coordinates would be silently misinterpreted — no crash, no error, just a board that's wrong in a way nothing would catch, which is worse than a loud failure.

- [x] Decide explicitly: either wire `origin`/`index_base` into `Position`/`Board` now, or document — in `PRD/PRD-1-base-logic.md`, not just here — that this codebase only ever supports the default and that any negotiation away from it is out of scope until fixed. Either answer is fine; leaving it undecided is not.

**Fixed — decided against wiring in a coordinate transform (bigger surface area, more to get wrong) in favour of a loud guard.** `GameConfig.from_dict` now raises `ValueError` if `origin != "top-left"` or `index_base != 0`. A negotiated deviation from the default now fails at config-load time with a message pointing back here, instead of silently misreading coordinates. Tests: `test_unsupported_origin_is_rejected`, `test_unsupported_index_base_is_rejected`, `test_default_origin_and_index_base_are_accepted`.

## 4. Untested — `GameConfig.from_dict` never rejects a nonsensical value

The only rejection test PRD 1 has for config is a *missing* field (`test_missing_required_field_raises`). Nothing proves what happens if `board_size` is `-1`, `"seven"`, or `0` — `GameConfig.from_dict` would happily construct the dataclass, and the first sign of trouble would be some downstream domain function behaving strangely, far from the actual bad input.

- [x] Either add range/type validation to `GameConfig.from_dict` with a rejection test, or add a test proving `check_config.py` is relied on to catch this instead and document that division of responsibility explicitly (right now it's implicit).

**Fixed.** `GameConfig.from_dict` now type/range-checks `board_size`, `barrier_quota`, `step_ceiling`, `survival_threshold`, and all four score fields via `_positive_int`/`_non_negative_int` helpers, raising `ValueError` (distinct from the existing `KeyError` for missing fields). Tests: `test_negative_board_size_is_rejected`, `test_non_integer_barrier_quota_is_rejected`.

## 5. Documentation imprecision — "all five end scenarios"

`PLAN.md` §5 PRD 1's "Also verify" line says "all five end scenarios score correctly per Table 17." Table 17 defines three *event types* — capture, survival, technical loss — each producing one (cop, thief) score pair; "five" appears to count the five *parameter rows* in Appendix F's Table 17 (capture_cop, capture_thief, survival_cop, survival_thief, draw), not five distinct end-of-subgame scenarios. `tests/unit/test_scoring.py` correctly tests three outcomes, which is right — but a reader hunting for a fifth scenario per the literal PLAN.md wording would go looking for something that doesn't exist.

- [x] Fix the wording in `PLAN.md` §5 PRD 1 to say "all three event types, covering all five Table 17 score values" or similar.

**Fixed.** `PLAN.md` §5 PRD 1 now reads "all three end-of-subgame outcomes (capture, survival, technical loss) score correctly against Table 17's five parameter values," and the barrier "also verify" clause was corrected to only claim what PRD 1 actually enforces (adjacency + bounds), not the still-deferred "forgo move" constraint.

## What this review did *not* find

No issues found in movement legality, capture detection, or the technical-loss score path — those held up under adversarial re-reading.

One item from `rule-auditor`'s original notes is **still genuinely deferred**, not fixed here, because fixing it requires something PRD 1 doesn't have: barrier "forgo move" enforcement (a cop must give up its move to place a barrier) needs turn state, which only exists once PRD 2's sequencer is built. That's correctly tracked as an open `[PRD 2]` item in `TODO.md`, not resolved in this pass — the off-board-bounds half of that original note *was* resolvable inside PRD 1's own scope (it didn't actually need turn state, just a `Board` reference), which is why it's fixed above instead of carried forward.

## Status: closed

All five findings fixed and re-verified: 52 tests passing (was 44), 100% coverage, `ruff check` clean, `check_config.py` 31/31, `scripts/watch_prd1.py` re-run live including the new bounds-check case. PRD 1 can now be considered actually done, not just automated-check-clean.
