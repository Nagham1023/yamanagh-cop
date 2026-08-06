# TODO4-revision — Build Checklist for PRD 4 Revision 1 (book-accurate scent + opponent-scent corroboration)

Done — all 10 sections built, tested, and verified. Mirrors `PRD-4-language-and-scent.md`'s "Revision 1" section, same specificity level as `TODO4.md`. Follows `TODO1.md`'s precedent: a post-hoc correction pass on an already-shipped, committed layer, not a new PRD number.

## 0. `memory/scent.py` — the core fix

- [x] Module-level `_KERNEL: dict[tuple[int, int], float]` — the 25 `(d_col, d_row) → value` pairs from Figure 4 (page 44), for the 5×5 case centred at `(0, 0)`: `(0,0)=0.90`; orthogonal `(±1,0)/(0,±1)=0.62`; diagonal `(±1,±1)=0.42`; range-two orthogonal `(±2,0)/(0,±2)=0.20`; range-two off-axis `(±2,±1)/(±1,±2)=0.14`; corners `(±2,±2)=0.04`.
- [x] Remove `emit()` and `decay()` entirely — replace with `advance(pos: Position, board: Board) -> None`: (a) decay every tracked cell by `1 - decay_rate`; (b) compute the source-strength-scaled kernel around `pos` (`_KERNEL` value × `source_strength / 0.9`), clipped to board bounds; (c) add the scaled kernel onto the decayed values; (d) floor every resulting value at 0.0. Matches `τ(t+1) = max(0, (1-ρ)·τ(t) + Δτ)` in one atomic step — no intermediate state where the fresh deposit has already been decayed.
- [x] Guard: `from_config`/`advance` raises a clear error if `window_size != 5` (the hardcoded kernel table has no meaning at another size; Table 16 marks `scent_field_size` FIXED, so this is a real invariant).
- [x] `sample()` unchanged in shape (still a windowed read over `_levels`), now reading real post-`advance()` data.
- [x] Docstring rewritten to cite ch. 4.3/Figure 4 directly and describe the field's two now-current purposes: self-search down-weighting (unchanged) and the honest source for the outgoing scent report (new).
- [x] `tests/unit/test_scent.py` rewritten (not extended): kernel values match Figure 4 exactly at every one of the 25 offsets; `advance()` correctly composes decay+emission (a cell with prior residual scent plus a fresh nearby deposit shows the summed, not overwritten, value); repeated `advance()` calls at a fixed point never go negative and never exceed a sane ceiling; a cell outside the 5×5 window around the current call gets decayed but no fresh deposit; boundary clipping near a board edge still holds (carried over from the original test's boundary case).
- [x] Rejection test: constructing/advancing with `scent_field_size != 5` raises.
- [x] Sanity-check: temporarily flatten the kernel to a single-cell point deposit (the old behaviour), confirm the new kernel-shape test fails, then revert — proves the test actually pins the radial shape, not just "some value at center."

## 1. `reasoning/hint.py` — scent-report generation, reusing existing interpretation

- [x] `dominant_scent_direction(sampled: dict[Position, float], own_pos: Position) -> tuple[str, str]`: among `sampled`'s cells (excluding `own_pos` itself), sum scent by quadrant sign relative to `own_pos` (`d_col`/`d_row` sign, same convention as `_quadrant`), return the `(vertical, horizontal)` pair with the highest sum. Graceful default (`("north", "west")`, matching `interpret_hint`'s own default) when the window is empty or exactly symmetric (e.g. turn 1, no residual history yet).
- [x] `generate_scent_report(sampled: dict[Position, float], own_pos: Position, config: GameConfig) -> str`: deterministic template, `"Scent strongest to the {vertical} {horizontal}."`, hard-capped at `config.hint_word_limit` (same backstop-truncation pattern as `generate_hint`). No `HintProvider`, no `intent` parameter — always truthful by construction, never routed through `choose_provider`/any LLM.
- [x] `interpret_hint` reused unchanged to parse an incoming scent-report string (vocabulary matches by design — no new parser).
- [x] Unit test: `dominant_scent_direction` on a manufactured asymmetric window (e.g. only north-east cells nonzero) returns `("north", "east")`.
- [x] Unit test: `dominant_scent_direction` on a fresh, perfectly symmetric window (immediately after one `advance()`, no prior history) returns the documented default, not a crash or an arbitrary pick.
- [x] Unit test: `generate_scent_report` never exceeds `hint_word_limit` even with an artificially tiny configured limit (same backstop-truncation proof `generate_hint`'s test already does).
- [x] Rejection test: `generate_scent_report`'s output never contains a digit (same coordinate-leak discipline as the existing `generate_hint` sweep — extend or mirror `test_generate_hint_never_produces_digits_that_look_like_coordinates`).

## 2. `memory/belief.py` — corroboration update

- [x] `update_from_scent_report(focal_point: Position, board: Board) -> None`: same shape as `update_from_hint` (boost focal cell + orthogonal neighbours, renormalize), new `_SCENT_REPORT_BOOST` constant, larger than `_HINT_BOOST` (documented as the same category of heuristic-tuning constant, not an Appendix F value — state the chosen ratio and why in the docstring, don't leave it a bare number).
- [x] Unit test: after `update_from_scent_report`, the distribution still sums to 1 and the focal region's probability increased.
- [x] Unit test: given a claim-boosted focal point and a *different*, scent-report-boosted focal point applied in sequence, the scent-report's region ends up with higher probability than the claim's — the actual "corroboration outweighs a lie" property, at the `BeliefMap` unit level before the full milestone test assembles it end to end.

## 3. Wire — `tools/mcp_server.py` / `tools/mcp_client.py`

- [x] `receive_hint(text: str, scent_report: str) -> dict`: validates and reports word counts for both fields independently against `config.hint_word_limit`; ack shape extended (e.g. `{"accepted": bool, "word_count": int, "scent_word_count": int}` — decide and document, matching the existing ack-shape-documentation discipline).
- [x] `send_hint(url: str, text: str, scent_report: str) -> dict`.
- [x] `build_server`'s `on_hint` callback signature becomes `Callable[[str, str], None] | None`.
- [x] Unit tests updated (not just extended) for the two-field shape: valid combined payload, one field over the word limit while the other isn't, non-string payload on either field, missing argument.
- [x] Rejection test carried over: calling with the wrong argument shape still raises `ToolError` (FastMCP schema enforcement, unchanged reasoning from the original build).

## 4. `Orchestrator`/`orchestrator_turn.py` — wiring

- [x] Budget the 150-line cap *before* writing (per the PRD's explicit warning — `orchestrator.py` is already at 145 lines). Likely shape: extract hint+scent-report generation/interpretation glue out of `orchestrator_turn.py`'s `take_turn()`/`_on_hint_received` into a small dedicated helper (module-level functions in `reasoning/hint.py` already do the pure-function work; the mixin should mostly be sequencing calls) rather than inlining more logic into either file.
- [x] `take_turn()`: `self.scent_field.advance(self.game_state.own_pos, self.board)` replaces the old `emit()`+`decay()` pair. Generate both `text` (existing) and `scent_report` (new, from `self.scent_field.sample(...)` + `dominant_scent_direction` + `generate_scent_report`) and send both via the extended `send_to_peer`/`send_hint`.
- [x] `_on_hint_received(self, text: str, scent_report: str) -> None`: interpret both via `interpret_hint`, apply `belief_map.update_from_hint(...)` (existing) *and* `belief_map.update_from_scent_report(...)` (new), log both.
- [x] Unit test: after `take_turn()`, both belief-map update paths have measurably fired (not just `game_state`/`scent_field` as the original test checked — now also confirm the scent-report text reached the peer, same "wiring is real" discipline).
- [x] Unit test: a live round-trip where the tactical claim and the scent report disagree (constructed scenario) — confirm both still cross the wire independently and both still get parsed/applied on the receiving end.

## 5. Milestone — extended, not just replaced

- [x] `tests/unit/test_belief_deception.py`: keep the original case (`Intent=False` shifts belief wrong, in isolation, no corroboration) — this still proves the claim channel alone remains corruptible.
- [x] Add a new case: same true position, `Intent=False` on the claim, *and* a truthful `generate_scent_report` from the same true `ScentField`/position. Apply `update_from_hint` (claim) then `update_from_scent_report` (truthful) to one fresh `BeliefMap`. Assert the true quadrant's probability now exceeds the lie's quadrant's probability — the corroboration mechanic actually working, not just present.
- [x] Sanity-check by sabotage: temporarily make `generate_scent_report` respect an `intent` flag too (i.e. let it lie like the claim), confirm the new corroboration test fails, then revert — proves "always truthful" is load-bearing in the test, not decorative. `git diff` confirms a clean revert afterward.

## 6. Grep-the-wire — extended to the scent-report field

- [x] Extend (or add a sibling to) `test_generate_hint_never_produces_digits_that_look_like_coordinates` so the same sweep (many true positions, both `Intent` values, `template` mode) also covers `generate_scent_report`'s output — no digit-looking coordinate pattern in either field, ever.

## 7. Mechanical fixups — every existing caller of the old two-arg-less shape

- [x] `tests/integration/_server_process.py`, `tests/integration/_helpers.py`, `tests/integration/test_concurrent_exchange.py`, `tests/integration/test_two_process_roundtrip.py` — updated for the `(text, scent_report)` signature, same style as PRD 4's original `col`/`row` → `text` mechanical pass.
- [x] `tests/unit/test_orchestrator.py`, `test_orchestrator_watchdog.py`, `test_orchestrator_peer_failures.py`, `test_orchestrator_take_turn.py` — updated call sites and assertions.
- [x] `scripts/watch_prd2_roundtrip.py` if it still references `send_hint`'s old single-field shape (confirm; update if so).

## 8. Live demo script

- [x] `scripts/watch_prd4_language.py` updated: show a lying claim, its truthful scent-report companion (from the same true position), and the net belief shift favoring the true position despite the lie — the corroboration mechanic, visibly running end to end. Keep the existing local-pursuit and one-real-round-trip sections, extended rather than replaced.
- [x] Watched live by a human.

## 9. Wrap-up

- [x] `uv run pytest` — full suite green, 100% coverage maintained.
- [x] `uv run ruff check .` — clean.
- [x] `check_config.py` — still 31/31 (no new config fields).
- [x] File line counts re-checked against the 150-line cap after the `orchestrator.py`/`orchestrator_turn.py` split from §4.
- [x] `rule-auditor` run specifically against rules 23, 26, 27 again (the wire surface changed a second time) plus I6/I9 — treat a clean pass as a hard gate, not a formality, given the fatal-rule stakes here. Found zero fatal violations and one real non-fatal I9 gap (pre-existing since the original PRD 4 build, touched again by this revision without being fixed): `_on_hint_received` applied both belief updates before checking either field respected `hint_word_limit`. Fixed — each field now gated independently on its own word count before it can touch belief state — and re-verified (212 tests, ruff clean).
- [x] Update `PRD/PRD-4-language-and-scent.md`'s "Revision 1" section with a short "Built & verified" addendum (mirroring the original's own retrospective style) once actually built — any real findings from construction go there, same honesty discipline as the original build.
- [x] Update `TODO.md`'s PRD 4 entry to note the revision and point at this file.
- [x] Own critical pass (only if something's actually found — don't manufacture findings for the ritual).
- [x] Commit only after all of the above — nothing gets marked done pre-commit (the original PRD 4's own rule-auditor finding on this exact mistake is the one not to repeat).
