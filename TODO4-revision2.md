# TODO4-revision2 — Build Checklist for PRD 4 Revision 2 (absolute-quadrant scent semantics)

Prospective — nothing below is built yet. Mirrors `PRD-4-language-and-scent.md`'s "Revision 2" section, same specificity level as `TODO4-revision.md`. A real bug fix to already-shipped, committed code, not a new layer — follows `TODO4-revision.md`'s own precedent (a post-hoc correction pass), same PRD → TODO → execute discipline. Do not start until this checklist itself has been reviewed.

## 0. Confirm the bug reproduces before touching anything

- [ ] Construct the counterexample directly against current `main`: `true_pos` in the board's south-west (e.g. `Position(1, 5)` on a 7-board), `previous_pos` to its north-east (e.g. `Position(3, 3)`). Call `dominant_scent_direction`/`generate_scent_report`/`interpret_hint` in sequence and confirm the resolved focal point lands in the board's north-east — the opposite corner from `true_pos`. This is the failing case the new tests below encode; confirming it fails *first*, by hand, is the same discipline as every other "found via reproduction" entry in this repo's PRDs.

## 1. `reasoning/hint.py` — the fix

- [ ] Replace `dominant_scent_direction(sampled, own_pos)`'s body: sum **every** cell in `sampled` (including `own_pos`, not excluding it) into four board-absolute quadrant buckets — same sign convention as `tools/hint_providers.py::_quadrant` (row/col compared against `board_size / 2`, not against `own_pos`). Keep the function name and signature (`sampled`, `own_pos`) unchanged if possible — `own_pos` is still needed to know *whose* mass this is, even though the bucketing is now absolute, not relative to it. Keep the `None` return for a genuinely all-zero window (Revision 1's no-signal sentinel) — that behavior is unaffected by this fix and must stay exactly as-is.
- [ ] Update the function's docstring to state the corrected semantics plainly: reports the absolute board quadrant where the sender's own scent mass (fresh deposit + residual history) is concentrated — not a relative trail-direction-from-self. Cite ch. 4.4's worked example directly (already quoted in the PRD's Revision 2 section) as the reason, and note the exclude-self relative version was Revision 1's bug, not a stylistic difference.
- [ ] `generate_scent_report`'s call site and word-limit truncation logic need no change — it already just formats whatever `dominant_scent_direction` returns.
- [ ] Confirm `interpret_hint` itself needs **no change** — the fix is specifically that the existing absolute-quadrant decoder becomes correct for the scent report too, not that a second decoder gets built. If any change to `interpret_hint` seems necessary while implementing this, stop and reconsider — that would mean the fix drifted from the plan.

## 2. Rebuild the tests around the SW counterexample

- [ ] `tests/unit/test_hint.py::test_dominant_scent_direction_on_an_asymmetric_window_finds_the_true_lean` — rewrite so the sampled window represents a real trail leading toward a board corner from the *opposite* direction (matching §0's counterexample geometry), and assert the returned quadrant matches the board-absolute quadrant containing `own_pos` — not the old relative-lean expectation.
- [ ] `tests/unit/test_hint.py::test_dominant_scent_direction_inside_the_window_argmax_lands_in_the_correct_quadrant` (added during PRD 5 hardening) — re-verify against the corrected semantics; likely already compatible since the "correct quadrant" it checks against should now mean *absolute*, but confirm the fixture's own true/previous position geometry doesn't happen to mask the fix the same way the original milestone fixture did.
- [ ] `tests/unit/test_belief_deception.py::test_a_truthful_scent_report_corroborates_against_a_lying_hint_and_wins` — change `true_pos` to a board south-west position (per §0), `previous_pos` to its north-east (an ordinary "moving into the corner" trajectory, the geometry that previously broke the mechanism). Strengthen the assertion: instead of only `belief.probability(truth_focal_point) > belief.probability(lie_focal_point)`, add an explicit assertion that `truth_focal_point` (the scent report's resolved focal point) is genuinely in the board's south-west (`row > board.size/2` and `col < board.size/2`, or equivalent), proving the argmax lands at the *true* region specifically — the exact strengthening the critique asked for.
- [ ] `tests/unit/test_orchestrator_take_turn.py::test_on_hint_received_applies_both_the_claim_and_the_scent_report` and any other test hardcoding a scent-report string like `"Scent strongest to the north west."` paired with a specific `own_pos` — audit each for whether the old relative-lean assumption was baked into the test's own expected values, and correct any that were.
- [ ] `scripts/watch_prd4_language.py`'s corroboration demo section — update `previous_pos`/`corroboration_true_pos` to the SW-counterexample geometry so the live demo shows the *fixed* mechanism working on the case that used to break it, not the original fixture that happened to work by coincidence.

## 3. Sanity-check the fix actually matters

- [ ] Sabotage: temporarily revert `dominant_scent_direction` to the exclude-self relative computation (Revision 1's version). Run the rebuilt SW-counterexample test from §2 and confirm it **fails** — proving the new, stronger assertion catches what the old "beats the lie's quadrant" assertion would have missed (that assertion should still *pass* even under the reverted/buggy version, since the lie and the wrong-corroboration-region are still different quadrants — the point is the *new* assertion is what distinguishes correct from buggy, not the old one). Revert the sabotage; confirm `git diff` is clean afterward.

## 4. Wrap-up

- [ ] `uv run pytest` — full suite green, 100% coverage maintained.
- [ ] `uv run ruff check .` — clean.
- [ ] `check_config.py` — still 31/31 (no config fields touched by this fix).
- [ ] File line counts re-checked against the 150-line cap (`reasoning/hint.py` was at 143 before this revision — the fix is a body replacement, not a large addition, but confirm).
- [ ] `rule-auditor` run against rules 23/26/27 and I6/I9 again — this touches the same wire-adjacent belief-update code those rules already cover; treat a clean pass as a gate, not a formality, matching Revision 1's own discipline for this exact module.
- [ ] Update `PRD/PRD-4-language-and-scent.md`'s Revision 2 section with a "Built & verified" addendum once actually built, same honesty discipline as Revision 1's own retrospective (including whether the fix landed exactly as planned or surfaced something further during construction).
- [ ] Update `TODO.md`'s PRD 4 entry to note Revision 2.
- [ ] Update `WIRE-CONTRACT.md`'s status log if this fix changes anything the teammate needs to know about (it shouldn't — the wire *shape* is unchanged, only the sender's own internal direction computation — but confirm before assuming).
- [ ] Own critical pass (only if something's actually found — don't manufacture findings for the ritual).
- [ ] Commit only after all of the above.
