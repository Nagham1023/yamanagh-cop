# TODO9 — Build Checklist for PRD 9 (Step-0 Negotiation Ceremony)

Status: **Done.** Read `PRD/PRD-9-step0-negotiation.md` in full first — its Design Questions section documents two decisions made *during* this build, not anticipated at design time (§3 below); this checklist reflects the corrected design, not a first draft.

## 1. `src/cop/integrity/scent_model_lock.py` — the scent-model hash (rule 23)

- [x] `compute_scent_model_hash(config: GameConfig) -> str` — canonical JSON of fixed formula description + `source_strength`/`decay_rate`/`field_size` + a worked numeric example, SHA-256'd (`integrity/canonical_json.py`, same discipline every other `integrity/` hash uses).
- [x] Worked example computed by actually running `ScentField.advance()` on an oversized synthetic board (kernel never clips) — emit once at `_SYNTHETIC_CENTER`, advance again at `_FAR_CELL` (more than one kernel radius away) so the second reading is pure decay, not decay-plus-a-new-overlapping-deposit.
- [x] Test: matches `WIRE-CONTRACT.md`'s own documented 0.9 → 0.81 worked example exactly, under the default Table 16 numbers.
- [x] Test: deterministic for the same config.
- [x] Rejection test: a different `scent_decay_rate` changes the hash; a different `scent_source_strength` changes the hash.
- [x] Test: unrelated config fields (e.g. `barrier_quota`) do **not** perturb the hash — this lock is scoped to the scent formula, not a restatement of `config_sha256`.

## 2. `src/cop/integrity/step0.py` / `report_bundle.py` — carrying the new field

- [x] `Step0Declaration` gains `scent_model_sha256: str`, non-empty-string validated in `__post_init__`, folded into `_canonical_declaration_bytes` (so `sign_step0` changes when it changes).
- [x] `report_bundle.py::build_declaration()` includes `scent_model_sha256` in the declaration file output (Table 20).
- [x] `scripts/watch_prd6_commit_reveal.py` updated to build and print it too — the one other place that constructs a real `Step0Declaration`.
- [x] Rejection test: an empty `scent_model_sha256` raises.
- [x] Test: `sign_step0` changes when only `scent_model_sha256` changes.

## 3. `src/cop/planner/state_machine.py` — `NEGOTIATING`

- [x] `NEGOTIATING` added to `TRANSITIONS`, legal targets `{WAITING_FOR_OPPONENT, TECHNICAL_LOSS}`.
- [x] **Corrected before writing this checklist's own tests, not after**: the first-pass idea of making `NEGOTIATING` the dataclass's own default state was rejected once its actual blast radius was checked — `Orchestrator.__init__` constructs `PeerStateMachine()` once, and every PRD 1-8 test that builds an `Orchestrator` and immediately drives `take_turn()`/`commit_and_reveal_to_peer` assumes it starts at `WAITING_FOR_OPPONENT`. Changing the default would have forced every one of those call sites to explicitly reset state first, for zero benefit. `negotiate_step0`/`_on_step0_received` each explicitly construct `PeerStateMachine(state="NEGOTIATING")` themselves instead — the dataclass default is untouched.
- [x] Test: `NEGOTIATING → WAITING_FOR_OPPONENT` legal.
- [x] Test: `NEGOTIATING → TECHNICAL_LOSS` legal.
- [x] Rejection test: `NEGOTIATING → COMMITTING` (skipping straight into the per-turn cycle) is illegal, state unchanged after the rejected attempt.
- [x] Full existing `test_state_machine.py` suite re-run — zero regressions, confirming the "don't touch the default" decision actually held.

## 4. `src/cop/tools/mcp_server_prd9.py` / `mcp_client_prd9.py` — the wire tool

- [x] `receive_step0(declaration: dict, signature: str, repos: dict) -> dict` — one synchronous round trip (Design Question 2: no reason for PRD 6's split-callback shape here, both sides already hold everything they need).
- [x] `send_step0(url, declaration, signature, repos) -> dict` client call, same thin shape as `mcp_client_prd6.py`.
- [x] Wired into `mcp_server.py::build_server` via a new `on_step0` callback parameter.
- [x] Test: tool registered; acks cleanly with no callback wired (tests exercising the rest of the surface aren't forced to stub this).
- [x] Test: `on_step0` fires with the exact received arguments and its return value is what the tool returns.
- [x] Test: a real HTTP round trip (`send_step0` against a real running server), not just in-process.

## 5. `src/cop/orchestrator_step0.py` — the ceremony itself

- [x] New mixin, `Step0NegotiationMixin`. `_build_own_step0()`, `_verify_peer_step0()` (the one check both directions run — malformed shape, then signature, then `config_sha256`, then `scent_model_sha256`, each raising `Step0MismatchError` with a specific logged reason), `_on_step0_received()` (responder), `negotiate_step0()` (initiator).
- [x] `integrity/step0_wire.py` split out (150-line cap) — `declaration_to_wire`/`declaration_from_wire`.
- [x] `Orchestrator.__init__` gains `shared_config_path: str = _DEFAULT_SHARED_CONFIG_PATH` and `self._opponent_repos: dict[str, str] | None = None`; `Step0NegotiationMixin` added to the class bases; `build_server(...)` gains `on_step0=self._on_step0_received`.
- [x] Test: two real `Orchestrator`s, matching config/formula — `negotiate_step0` succeeds, both state machines reach `WAITING_FOR_OPPONENT`, both learn each other's real repos.
- [x] Rejection test: mismatched `config_sha256` (different bytes on disk, same logical config) — both sides independently reach `TECHNICAL_LOSS`, `negotiate_step0` raises.
- [x] Rejection test: mismatched `scent_model_sha256` (identical config file, a genuinely different `scent_decay_rate` in the object driving `ScentField`) — same rejection, proving the scent lock is checked independently of `config_sha256`.
- [x] Rejection test: a forged/tampered signature is rejected on its own, without needing a hash mismatch to also be present.
- [x] Rejection test (added after `rule-auditor`'s own PRD 9 pass, see below): a malformed `repos` payload — a missing required key, a non-string value — is rejected by `_verify_peer_step0` itself, never reaches `self._opponent_repos` unchecked.

## 6. `src/cop/orchestrator_end_of_game.py::report_game` — rule 49's channel

- [x] `opponent_cop_repo_url`/`opponent_thief_repo_url` become optional (`= None`), moved after the now-required params for a clean signature; new `_opponent_repo_url(role)` helper raises `ValueError` (not a silent empty string) when neither an explicit override nor `self._opponent_repos` is available.
- [x] Test: sourced correctly from a completed negotiation (spied on the actual `ResultBundle` built, not just "didn't raise").
- [x] Test: an explicit override still wins over a completed negotiation.
- [x] Rejection test: raises with a clear message when neither is available.

## 7. `scripts/watch_prd9_step0_negotiation.py`

- [x] Two real `Orchestrator`s: a genuine successful `negotiate_step0()` over real HTTP, printed stage by stage (both state machines' final state, both sides' learned repos).
- [x] A second, adversarial run: one side's shared config file tampered by a single trailing byte, `negotiate_step0` raises, both state machines print `TECHNICAL_LOSS` — run and watched, not just asserted.

## Found only by actually running this layer

- **`rule-auditor`, scoped to rules 5/9/11/18/19/23/24/49, found one real gap**: `self._opponent_repos = dict(repos)` (both `_on_step0_received` and `negotiate_step0`) stored a peer's `repos` payload with zero shape validation — a missing `"cop"`/`"thief"` key or a non-string value would have surfaced as an uncaught `KeyError` inside `report_game()` at the end of a real match, not the clean `Step0MismatchError` path every other malformed-input case in this layer gets. Fixed: `integrity/step0_wire.py::validate_repos()`, folded into `_verify_peer_step0`'s existing malformed-shape check — see `PRD-9-step0-negotiation.md`'s own Retrospective for the full finding and fix.
- **A pre-existing, unrelated test failure**, unmasked while confirming a clean baseline before this layer's own tests were trusted: `test_private_config.py::test_loads_the_dev_private_config_from_disk` asserted the old placeholder repo URL (`https://github.com/dev-team/cop-repo`) even though `config/game.toml` was updated to the real, confirmed URL (`https://github.com/Nagham1023/yamanagh-cop`) in the immediately preceding commit (`f6397bf`, "docs: confirm the real thief-repo URL"). Confirmed via `git stash` that this fails identically on `main` at that commit, with none of this PRD's own changes present — not a regression this layer introduced. Fixed as a one-line, in-scope drift correction, not left for a separate pass.
- **The full `uv run pytest` suite needs splitting into batches** to get a reliable result in a reasonable wall-clock time — matches TODO8's own already-documented "run in split batches, as anticipated" note (real HTTP servers across ~450 tests add up); not a new finding, just re-confirmed still true at this layer's size.

## Cleanup and final verification

- [x] Every new/touched module re-checked against the 150-line house cap — `orchestrator_step0.py` needed the `step0_wire.py` split; `orchestrator.py` needed three docstring/comment trims to stay at 149 after the new constructor parameter and callback landed.
- [x] Full `uv run pytest`, run in batches — 455 unit tests + 8 integration tests green, 99% combined coverage on `src/cop` (`fail_under=85` cleared with room to spare).
- [x] `uv run ruff check .` — clean.
- [x] `check_config.py config/shared/config_dev_g01.json` — still 33/33.
- [x] `scripts/watch_prd9_step0_negotiation.py` run and watched — both cases confirmed live, output matches the Milestone's own description exactly.
- [x] `git log --all --full-history -- '*credentials*' '*token.json*' '*.env'` — still empty.
- [x] `WIRE-CONTRACT.md`'s ch. 4.5 section updated from "still not built" to describe the shipped ceremony; new `receive_step0` section added matching the existing per-tool documentation format.
- [x] `TODO.md`'s own master checklist — PRD 9 section added.
- [x] `PRD/PRD-9-step0-negotiation.md` written, built, and verified against this checklist; commit.
