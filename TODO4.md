# TODO4 — Build Checklist for PRD 4 (Language and Scent)

Done — all 12 sections built, tested, and verified. Mirrors `PRD-4-language-and-scent.md`'s scope and its seven Design Questions; see that document's "Built & verified" section for what changed versus this checklist's original plan (the PRD 3 seam turned out to have three non-seam sites, not one; an `on_hint` callback was added to feed incoming hints into the belief map).

## 0. Setup

- [x] `src/cop/shared/config.py`: extend `GameConfig` with `arena: str`, `hint_word_limit: int`, `scent_source_strength: float`, `scent_decay_rate: float`, `scent_field_size: int`. Validate each the same way existing fields are (`_positive_int`/`_positive_number`/a new `_non_empty_str` if `arena` needs one — decide and document; `arena` may legitimately be `""` per Table 14 #1's "generic landmarks" note, so a "non-empty" validator would be wrong).
- [x] Rejection test: missing/invalid values for each new field raise, matching `test_config.py`'s existing pattern.
- [x] `config/private/` directory created; a first private config file, e.g. `config/private/trash_talk_dev.json`, with `{"provider": "template", "every_n_steps": 1}` — not committed to the *shared* negotiation flow, never diffed by `check_config.py --identical`.
- [x] `src/cop/shared/private_config.py`: a small loader (`PrivateConfig` dataclass or similar) reading `provider`/`every_n_steps`, deliberately not reusing `GameConfig.from_file` (Design Question 7 — keep the private/negotiated split real, not just documented).
- [x] Confirm `check_config.py config/shared/config_dev_g01.json` is still 31/31 after `GameConfig` extension (the file doesn't change; only the code reading it does).

## 1. Close the PRD 2 carve-out (rule 26/27)

- [x] `tools/mcp_server.py`: remove `receive_position(col, row)` entirely (the `RULE-27-REMOVE-AT-PRD-4`-marked tool). Add `receive_hint(text: str) -> dict` — accepts a natural-language string, returns an acknowledgement (e.g. `{"accepted": True, "length": len(text)}` or similar; decide the ack shape and document why).
- [x] `tools/mcp_client.py`: remove `send_position`, add `send_hint(peer_url: str, text: str) -> dict`.
- [x] Delete `tests/unit/test_mcp_server.py::test_the_numeric_position_tool_is_gone_once_prd4_lands` and its `xfail` marker — this is the commit that makes rule 27's removal real, not something to keep deferring.
- [x] `grep -rn RULE-27-REMOVE-AT-PRD-4 src/ tests/` returns nothing once this section is done.
- [x] Unit test: `receive_hint` decodes a valid string payload correctly.
- [x] Rejection test: `receive_hint` rejects a non-string payload (matching the existing `test_receive_position_rejects_a_non_integer_column`-style coverage for the new tool).
- [x] Rejection test: an over-`hint_word_limit` string — decide here whether the *tool* rejects it or whether word-limit enforcement is purely the *sender's* job (§7) and the tool stays permissive (receiving is inherently "untrusted input," I9 — document the choice either way, don't leave it implicit).

## 2. `memory/scent.py` — `ScentField`

- [x] `src/cop/memory/__init__.py` — module docstring only.
- [x] `ScentField` class: `emit(pos: Position) -> None` (deposits `config.scent_source_strength` at `pos`), `decay() -> None` (multiplies the whole field by `1 - config.scent_decay_rate`), `sample(center: Position, board: Board) -> dict[Position, float]` (returns the `scent_field_size`×`scent_field_size` window around `center`, clipped to board bounds).
- [x] All three constants sourced from `GameConfig`, never a literal (I6) — this is what "also verify: scent constants match Table 16 exactly" is checking against, at the code level.
- [x] Docstring: state explicitly (Design Question 1) that this is the cop's *own* trail, used to down-weight its own recently-searched cells — not a signal received from or about the opponent.
- [x] Unit test: `emit` then `sample` shows the emitted cell at `scent_source_strength`.
- [x] Unit test: one `decay()` call reduces a previously-emitted cell by exactly `scent_decay_rate` proportionally (e.g. `0.9 * (1 - 0.10) == 0.81`).
- [x] Unit test: `decay()` applied repeatedly asymptotically approaches zero, never negative.
- [x] Rejection/boundary test: `sample` near a board edge returns only in-bounds cells, doesn't crash or wrap.

## 3. `memory/belief.py` — `BeliefMap`

- [x] `BeliefMap` class: constructed uniform over all `board_size × board_size` cells (Design Question 2 — **not** seeded from `config.thief_start`). `update_from_scent(scent_field: ScentField, cop_pos: Position, board: Board) -> None` down-weights cells with fresh scent. `update_from_hint(signal: ...) -> None` shifts mass toward the interpreted hint region. `normalize() -> None` (or called internally after every update) renormalizes to sum to 1. `most_likely_cell() -> Position` returns the argmax cell.
- [x] Decide and document the exact update math (a real Bayesian posterior, or a simpler weighted-reweighting scheme — either is defensible for this layer; don't leave the choice implicit in code with no explanation).
- [x] Unit test: freshly constructed `BeliefMap` sums to 1 and is uniform.
- [x] Unit test: after `update_from_scent`, the distribution still sums to 1 (renormalization didn't silently break), and the cop's own recently-scented cells have *lower* probability than before.
- [x] Unit test: after `update_from_hint` with a signal pointing at a specific region, that region's probability mass increases and the map still sums to 1.
- [x] Rejection test: an update that would produce a non-normalized or negative-probability state is either impossible by construction or explicitly caught — pick one and test it, don't leave an untested "can't happen."
- [x] Unit test: `most_likely_cell()` returns the actual argmax, not just "a" cell — construct a distribution with a known, deliberate peak and assert on it.

## 4. `tools/hint_providers.py` — the `[trash_talk] provider` abstraction

- [x] A `HintProvider` protocol/ABC: `generate(true_pos: Position, intent: bool, arena: str, word_limit: int) -> str`.
- [x] `TemplateHintProvider` — fully implemented, zero tokens, pre-written sentence templates referencing `arena` landmarks when `arena` is non-empty, generic phrasing when it's `""` (Table 14 #1's own carve-out). Must never exceed `word_limit`.
- [x] `OllamaHintProvider` — plain HTTP POST to `localhost:11434`, gracefully raises a clear, catchable error if unreachable (don't let a missing local Ollama install crash the whole turn silently or hang past a reasonable timeout).
- [x] `OllamaHintProvider`'s system prompt explicitly states `hint_word_limit` as an instruction to the model (Table 14 #2: "applies to template mode **and to the LLM (stated in its system prompt)**") — not just enforced as a post-hoc Python truncation in `reasoning/hint.py`. Unit test: the constructed prompt string sent to Ollama contains the configured word-limit number.
- [x] `ClaudeApiHintProvider`/`ClaudeCliHintProvider` — interface classes only, `generate()` raises `NotImplementedError` with a message pointing at Design Question 6 (no Gatekeeper yet). Selectable via `[trash_talk] provider` config without special-casing — the point of building the stub is that config validation doesn't need to know these are unfinished.
- [x] A factory function (`build_provider(name: str) -> HintProvider`) reading the private config's `provider` string.
- [x] Unit test: `TemplateHintProvider` never exceeds `word_limit` across a range of `(true_pos, intent, arena)` combinations.
- [x] Unit test: `TemplateHintProvider` output differs between `intent=True` and `intent=False` in a way that's at least directionally checkable (e.g. references a different quadrant/landmark) — this is what §7's tests build on.
- [x] Rejection test: `build_provider` with an unrecognized provider name raises, doesn't silently fall back to `template`.
- [x] Test (skip-if-unavailable is fine): `OllamaHintProvider` against a real local Ollama instance if the test environment has one; otherwise document that this path is exercised manually, not in CI.

## 5. `reasoning/hint.py` — generate + interpret

- [x] `decide_intent(...) -> bool`: the Intent-choosing policy. Can be simple (e.g. config-driven lie probability, or a fixed default) — the requirement is that it's *callable with a forced value* for testing (the milestone needs to construct `Intent=False` deterministically), not that it's strategically sophisticated (Design Question in `PRD-3...` precedent: heuristic quality is a later-PRD concern, per `PLAN.md`'s own "optional if time permits" framing for strategy refinement).
- [x] `generate_hint(true_pos: Position, provider: HintProvider, config: GameConfig, intent: bool) -> str`: calls the provider, enforces `hint_word_limit` as a hard backstop even if the provider itself already tries to respect it (never trust a single layer of enforcement for a fatal rule).
- [x] `choose_provider(step_number: int, configured_provider: HintProvider, template_provider: HintProvider, every_n_steps: int) -> HintProvider`: wires Table 21's `every_n_steps` (currently loaded in §0 but never consulted anywhere — a real gap, not a hypothetical one). On a step that isn't a multiple of `every_n_steps`, return the zero-cost `template` provider regardless of what's configured; on a cadence step, return the configured provider. `Intent` is still chosen and still logged every turn (§6) — only *which provider renders the text* is throttled.
- [x] `interpret_hint(text: str, board: Board) -> <signal type>`: parses incoming text into whatever `BeliefMap.update_from_hint` consumes — simple, deterministic keyword/direction matching is enough for the milestone (Design Question 4's local-testability point depends on this being callable without an LLM).
- [x] Unit test: `generate_hint` with `intent=False` produces text that, when independently checked against the true position, is misleading in a checkable way (e.g. references the wrong quadrant).
- [x] Unit test: `interpret_hint` on a hint referencing a specific region produces a signal that shifts `BeliefMap` toward that region when applied (this is the milestone's mechanism, tested at the unit level before the milestone test assembles it end-to-end).
- [x] Unit test: `choose_provider` returns the `template` provider on an off-cadence step even when a different provider is configured, and the configured provider on a cadence step — proves `every_n_steps` is actually consulted, not just parsed.
- [x] Rejection test: `generate_hint` never produces a string containing digits that look like coordinates (a first, cheap check — §9's sweep is the systematic, non-bypassable version of this).

## 6. Orchestrator wiring

- [x] `Orchestrator.__init__` gains `self.scent_field: ScentField`, `self.belief_map: BeliefMap`, `self.hint_provider: HintProvider` (built from the private config).
- [x] `orchestrator_turn.py`'s `BrainTurnMixin.take_turn()` reworked: `self.game_state.target_pos` now comes from `self.belief_map.most_likely_cell()` (Design Question 3 — **not** `ground_truth_target_position` anymore, that call site is deleted here specifically). `CopBrain._decide_move` itself is unchanged — it still just receives a `target_pos: Position`, agnostic to whether it's truth or a belief.
- [x] After the cop's own move is decided/applied, call `self.scent_field.emit(self.game_state.own_pos)` and `self.scent_field.decay()`, then `self.belief_map.update_from_scent(...)`.
- [x] `take_turn()` generates a hint (§5, via `choose_provider` — not the raw configured provider directly) and sends it via `send_hint` instead of the old `(col, row)` `send_to_peer` call — decide whether `send_to_peer` is renamed/repurposed or a new `send_hint_to_peer` method is added; keep `orchestrator.py`/`orchestrator_turn.py` under the 150-line cap either way (both are already close; budget for this before writing, not after).
- [x] After generating a hint, `self.trace.log("hint_generated", intent=intent, ...)` — operationalizes the PRD's own "Explicitly out of scope" promise that "the Intent flag is generated and locally recorded this layer (so PRD 6 has something real to reveal later)." Log the flag and turn metadata; do not log the hint's *truthful* content differently from its *sent* content — the trace records what was decided, not a second channel that could itself leak ground truth. Unit test: after `take_turn()`, the trace log contains a `hint_generated` entry with the correct `intent` value.
- [x] Watch the 150-line house cap on both files specifically — this section is the most likely to blow it, given PRD 3 already needed one mixin split at a smaller diff than this.
- [x] Unit test: `take_turn()` sends a string, not integers, over the wire (a live round-trip against a real peer, same style as PRD 3's `test_orchestrator_take_turn.py`).
- [x] Unit test: after `take_turn()`, `self.belief_map` and `self.scent_field` have both been updated (not just `game_state`) — proves the wiring reaches all three, not just the move.

## 7. Local milestone test — the core proof, no network

- [x] `tests/unit/test_belief_deception.py` (or similar): construct a scenario with a known true cop position, force `Intent=False` via `decide_intent`'s test-injection point, generate a hint, interpret it, apply it to a fresh `BeliefMap`, and assert the resulting most-likely region is measurably *wrong* relative to the true position — not just "different from uniform."
- [x] Same test (or a paired one): apply several `ScentField.decay()` cycles across the same scenario and assert the scent values decay by exactly the configured rate each step, *independent* of whatever the hint did to `BeliefMap` — proving the two channels are observably decoupled (the milestone's own "independent" language, made concrete).
- [x] This test must not spin up an `Orchestrator`, a server, or a subprocess — pure function calls over `memory/`+`reasoning/hint.py`, matching PRD 3's `reasoning/subgame.py` precedent exactly.

## 8. Wire proof — the wiring is real, kept separate from milestone

- [x] One real localhost round-trip proving `take_turn()`'s outgoing hint reaches `receive_hint` and decodes correctly — landed in `tests/unit/test_orchestrator_take_turn.py` (e.g. `test_take_turn_moves_according_to_the_brains_own_decision_not_a_fixed_position`) rather than a separate `test_orchestrator_hint_wiring.py` file, since PRD 3's existing take-turn test file already carries this exact wiring-is-real discipline for the same method (rule-auditor flagged the original file-name mismatch; corrected here rather than duplicating the test into a second file).
- [x] Rejection test: calling the hint-sending path from an illegal state machine state still raises (rule 5 enforcement carried over unchanged from PRD 2/3 — confirm it, don't assume the rewiring preserved it).

## 9. "Grep the wire" — systematic coordinate-leak sweep (Design Question 5)

Simplified from the original plan to intercept raw serialized HTTP/JSON bytes: the `text` field's string value *is* exactly what gets JSON-serialized onto the wire, byte for byte (escaping doesn't change digit sequences) — grepping the string is grepping the wire, without building custom transport-layer interception for no added certainty. The genuinely stronger, protocol-level guarantee — no numeric position parameter can reach the wire *at all* — is already provided by §1 removing `receive_position`/`send_position`'s tool signatures entirely; that's a fact about the MCP schema, not something a grep proves.

- [x] §5's single rejection test scaled into a full sweep — landed as `tests/unit/test_hint.py::test_generate_hint_never_produces_digits_that_look_like_coordinates` rather than a separate `test_no_coordinates_on_the_wire.py` file, since `reasoning/hint.py`'s own test file already owns `generate_hint`'s coverage. Sweeps every board position × both `Intent` values via `template` mode, grepping every generated string for a coordinate-like digit. Satisfies `PLAN.md`'s literal "grep the wire, do not trust inspection" instruction — systematic checking, not eyeballing one example — without transport-layer interception machinery (rule-auditor flagged the original file-name mismatch; corrected here).
- [x] Confirm this test would actually fail against a deliberately-broken hint generator (temporarily make `TemplateHintProvider` interpolate raw coordinates into its template, confirm the test catches it, then revert) — same sanity-check discipline as PRD 2's concurrency check and PRD 3's milestone check.

## 10. Update `test_prd4_seam.py` for the (partial) seam change

- [x] Per Design Question 3: revise the AST check so it asserts `subgame.py`'s two `target_pos=`/`.target_pos =` sites still call `ground_truth_target_position` (unchanged, still correct for local algorithm testing) **and** `orchestrator.py`'s site does **not** call it anymore — a positive assertion that the swap happened, not a check that merely stopped failing.
- [x] Keep `test_the_seam_function_itself_exists_and_is_currently_the_identity` — `ground_truth_target_position` itself is unchanged; only who calls it changed.
- [x] `GameState`'s `kw_only=True` guard (PRD 3's review-pass fix) needs no changes — still applies.

## 11. Live demo script (`scripts/watch_prd4_language.py`)

- [x] Same two-section spirit as `watch_prd3_brain.py`: (1) local — generate a truthful hint and a lying hint from the same true position, print the interpreted belief shift for each, print several scent decay steps, no subprocess; (2) one real round-trip — spin up a real peer (reusing the existing `_server_process.py`-style helper, updated for `receive_hint`), call `take_turn()` once, print the actual hint text that reached the peer.
- [x] Exact terminal run command documented in the script's own docstring and added to `TODO.md`'s "Demo scripts" block.

## 12. Wrap-up

- [x] `uv run pytest` — full suite green, coverage ≥85% (aim for the 100% this repo has held since PRD 1)
- [x] `uv run ruff check .` — clean
- [x] `check_config.py` — still 31/31 against `config/shared/config_dev_g01.json`
- [x] File line counts: every new/touched file under the 150-line house cap — budget the `orchestrator.py`/`orchestrator_turn.py` split *before* writing, not after (§6's own warning)
- [x] `grep -rn RULE-27-REMOVE-AT-PRD-4 src/ tests/` returns nothing
- [x] `rule-auditor` run specifically against rules 23, 26, 27, and I6/I9 on the new `memory/`/`tools/hint_providers.py`/`reasoning/hint.py` code
- [x] Watch `scripts/watch_prd4_language.py` run live, end to end, by a human
- [x] Sanity-check the milestone the way PRD 2's concurrency claim and PRD 3's heuristic claim were checked: temporarily break `interpret_hint` (e.g. make it ignore the text and return a no-op signal) and confirm the deception milestone test actually fails. Then revert.
- [x] Update `PRD/PRD-4-language-and-scent.md` — flip status to Done, add a retrospective "Built & verified" section
- [x] Update `TODO.md` — PRD 4 row to done, demo script command added
- [x] Own critical pass, `TODO1.md`/`TODO2.md`/`TODO3.md`-style but retrospective (only if something's actually found — don't manufacture findings for the sake of the ritual)
- [x] Commit
