# TODO6 — Build Checklist for PRD 6 (Security and Cryptography)

Not started. Largest, most fatal-rule-dense layer in the project — read `PRD-6-security-and-cryptography.md`'s "Design questions answered here" section in full before writing any code in this checklist; several sections below depend directly on design calls made there (especially DQ1's envelope shape and DQ2's "Move is an unverified claim until Final Reveal" resolution).

## 0. Setup

- [ ] Re-read `PRD-6-prep-commit-payload-spec.md` and `src/cop/integrity/commit_payload.py` in full — confirm `canonical_state_bytes()`'s frozen field list still matches what's in the repo (nothing since should have touched it) before building on top of it.
- [ ] Confirm `src/cop/integrity/__init__.py` exists and is still docstring-only (it is, from the prep pass) — new modules this layer adds go alongside `commit_payload.py`, not replacing it.
- [ ] Re-confirm via `grep -rn RULE-15-16-BARRIER-DECLARATION-AT-PRD-6 RULE-21-22-CAPTURE-CLAIM-AT-PRD-6 RULE-19-SCENT-AUDIT-AT-PRD-6 src/ tests/` that all three markers are exactly where the summary says (`domain/barriers.py`, `domain/capture.py`, `orchestrator_turn.py`, the three guard test files) — know the exact deletion targets before starting.
- [ ] Read `tests/unit/test_prd6_missing_wire_channels_guard.py` and `tests/unit/test_prd6_scent_audit_guard.py` one more time immediately before starting — they name exact expected APIs (`receive_barrier_declaration` tool name, `cop.integrity.capture_protocol.claim_capture`/`respond_to_capture_claim`, `cop.integrity.audit.verify_scent_map_against_commit`) that this checklist's function signatures must match exactly, or the guards won't actually XPASS when this lands.

## 1. `integrity/nonce.py`

- [ ] `generate_nonce() -> str`: `secrets.token_hex(16)`. One function, nothing else — exists so no other module in `integrity/` reaches for `random` or hand-rolls hex generation.
- [ ] Test: `generate_nonce()` returns a 32-character hex string (16 bytes).
- [ ] Test: two calls produce different values (not a hardcoded/seeded stub).
- [ ] `rule-auditor`-style grep check as a test, not just a manual step: `grep -rn "^import random\|^from random" src/cop/integrity/` returns nothing — a real, automated rejection test for this specific module, not just a general repo-wide sweep.

## 2. `integrity/commit_reveal.py` — the book's own `commit()`/`verify()`, extended to this repo's real envelope

- [ ] Design the envelope dataclass first (PRD's DQ1): `CommitEnvelope` with fields `state: bytes` (already-canonicalized, from `commit_payload.canonical_state_bytes`), `move: dict`, `intent: bool`, `nonce: str`, `hint_text: str`, `step: int`, `role: str` (literal `"cop"`, a module constant — this repo is never `"thief"`, rule 1/2).
- [ ] `_canonical_envelope_bytes(envelope: CommitEnvelope) -> bytes`: builds the flat 7-key dict (`state` decoded back to a JSON-parseable structure or kept as an already-serialized sub-value — decide precisely: since `state` is already canonical JSON bytes from §0's confirmed spec, embedding it as a raw JSON *string* value inside the outer envelope, not re-parsed, keeps `canonical_state_bytes`'s own byte-for-byte guarantee intact end-to-end), canonical `json.dumps(..., sort_keys=True, separators=(",", ":"))`, UTF-8 encoded. Reuse `commit_payload.py`'s `_CANONICAL_JSON_KWARGS` constant rather than redefining it — extract it to a small shared location if both modules need it (check the 150-line cap before deciding whether this warrants its own tiny `_canonical.py`, or just import it from `commit_payload`).
- [ ] `commit(envelope: CommitEnvelope) -> str`: returns `Hcommit` — `hashlib.sha256(_canonical_envelope_bytes(envelope)).hexdigest()`. Matches ch. 5.3.1's own worked `commit()` shape (p.53) but built on this repo's real 7-field envelope, not the illustrative 4-field one.
- [ ] `verify(envelope: CommitEnvelope, h_commit: str) -> bool`: recomputes and compares via `secrets.compare_digest`, never `==` — same as p.53's own `verify()`.
- [ ] Test: `commit()` on the same logical envelope, constructed two different ways (e.g. barrier list built in a different insertion order, same logical state), produces byte-identical `Hcommit` — direct extension of `test_commit_payload_spec.py`'s own discipline to the full envelope.
- [ ] Test: changing *any single field* (state, move, intent, nonce, hint_text, step, role) changes `Hcommit` — proves every field is actually load-bearing in the hash, not silently ignored.
- [ ] Test: `verify()` returns `True` for a genuine `(envelope, h_commit)` pair and `False` for a tampered one — and confirm it uses `secrets.compare_digest` specifically (inspect the source, or monkeypatch `secrets.compare_digest` and confirm it's actually called, not `==`).
- [ ] Rejection test: `verify()` against an envelope with one field changed after `commit()` was called → `False`, not a crash.

## 3. `planner/state_machine.py` — extend `TRANSITIONS`

- [ ] Build the book's own table first, verbatim (Fig. 11, p.80, re-read directly for PRD DQ4 — not paraphrased):
  ```python
  TRANSITIONS = {
      "WAITING_FOR_OPPONENT": {"COMPUTING_MOVE"},
      "COMPUTING_MOVE": {"COMMITTING", "TECHNICAL_LOSS"},
      "COMMITTING": {"AWAITING_REVEAL"},
      "AWAITING_REVEAL": {"VERIFYING", "TECHNICAL_LOSS"},
      "VERIFYING": {"WAITING_FOR_OPPONENT"},
      "TECHNICAL_LOSS": set(),  # terminal state
  }
  ```
  Rename the existing states to match the book's own vocabulary — `SENDING`→`COMMITTING`, `AWAITING_RESPONSE`→`AWAITING_REVEAL` — since they're the same conceptual slot in the cycle, not two different things. `VERIFYING` is a **new** state, not a rename of anything existing. There is no `TURN_RESOLVED` state anywhere in the book or in this table — do not add one. Grep every call site (`orchestrator_peer.py`'s `send_to_peer`, all its tests) before editing, since the rename touches every test asserting on the literal state string.
- [ ] `VERIFYING` **is** added to the per-turn `TRANSITIONS` table (PRD DQ4, corrected) — `AWAITING_REVEAL → VERIFYING → WAITING_FOR_OPPONENT` fires every turn, matching Fig. 11's own cyclic caption (p.79). It is a **lightweight, structural** check only (reveal arrived, well-formed, claimed move locally legal) — it cannot recompute `Hcommit` because the nonce isn't available until Final Reveal (rule 18). The full cryptographic mutual audit stays exactly what DQ2 already designed: a separate, one-time `integrity/audit.py::run_mutual_audit` call at game end, outside `PeerStateMachine` entirely — not a state in this table.
- [ ] **Only extend the book's own table by one edge**, not a blanket "every state reaches `TECHNICAL_LOSS`": add `COMMITTING → TECHNICAL_LOSS` (a send that can itself hang or fail, same risk shape as the pre-PRD-6 `SENDING`→`TECHNICAL_LOSS` edge this repo already had) alongside the book's own two edges (`COMPUTING_MOVE`, `AWAITING_REVEAL`). Leave `VERIFYING` and `WAITING_FOR_OPPONENT` without an edge to `TECHNICAL_LOSS`, matching the book's own literal table — neither represents an active wait on a pending peer response. Document this as an argued, explicit deviation (Fig. 11's own caption calls dashed arrows broader "emergency exits" than its own code table wires up — an internal book contradiction; this repo's resolution favors the narrower literal table plus rules 6/7's independent watchdog requirement) in the module's own docstring, not silently.
- [ ] Update `state_machine.py`'s own module docstring citation now that the shape is real, not aspirational — cite Fig. 11 p.79-80 precisely, and note the one added edge as this repo's own extension.
- [ ] Test: the renamed/extended transition table still rejects an illegal transition (rule 5) — re-run the existing illegal-transition test with updated state names, confirm it still fails correctly.
- [ ] Test: `VERIFYING` is reachable from `AWAITING_REVEAL` and only transitions to `WAITING_FOR_OPPONENT` — proves the per-turn cycle is wired as designed, not accidentally omitted.
- [ ] Test: `COMMITTING` has exactly one legal successor plus the new `TECHNICAL_LOSS` edge; `VERIFYING` and `WAITING_FOR_OPPONENT` have no `TECHNICAL_LOSS` edge at all — proves the narrower, argued position was actually implemented, not the blanket one.
- [ ] Grep every test file for the old state-name strings (`"SENDING"`, `"AWAITING_RESPONSE"`) and update every occurrence — this will touch many existing test files across `tests/unit/test_orchestrator*.py`, `tests/integration/*.py`; budget real time for this, it's not a small edit.

## 4. `integrity/step0.py`

- [ ] `HardwareDeclaration` dataclass: `os_name: str`, `cpu_cores: int`, `ram_gb: float`, `gpu_present: bool`, `gpu_vram_gb: float | None`, `llm_model: str` — ch. 5.5's own field list (p.55), sourced from `platform`/`psutil`-equivalent stdlib calls where possible (decide: does this need a new dependency, or can `os.cpu_count()`/`platform.system()` cover it without one? RAM/GPU detection may need something — investigate before assuming a new dependency is required, and if one is, that's a real "New dependency" line PRD 6's own doc currently says isn't needed — reconcile).
- [ ] `Step0Declaration` dataclass: `hardware: HardwareDeclaration`, `code_commit_hash: str` (rule 53 — the actual git commit hash HEAD is at when this runs; `git rev-parse HEAD` via `subprocess`, or read from an env var/file set at deploy time — decide which, document why), `group_name: str`, `sub_game_number: int` (ch. 5.5's own "game number" field, p.55 — named to match `config/game.toml`'s existing `[game].sub_game_number` field, not a generic `game_id` string). Plus one field the book's own Step-0 list does not include: `config_sha256: str` — this repo's own extension to close rule 11's enforcement gap (Design Question 3), not a book-mandated field; label it as such in the dataclass's own docstring, same discipline as the belief-map reliability coefficient.
- [ ] `sign_step0(declaration: Step0Declaration) -> str`: canonical-JSON-serializes and SHA-256-hashes the declaration, same discipline as everything else in `integrity/`.
- [ ] `Step0Declaration` gets its own canonical serializer, same float-rejection discipline as `commit_payload.py` — `ram_gb`/`gpu_vram_gb` are floats by nature; decide how they're represented in the signed payload without falling into the exact trap `PRD-6-prep-commit-payload-spec.md` exists to prevent (round to a fixed precision and represent as a string at serialization time, matching that doc's own prescribed mitigation for "if a float has to be in there").
- [ ] Test: `sign_step0` on the same logical declaration, constructed twice, is byte-identical (same discipline as §2's envelope test).
- [ ] Test: `code_commit_hash` genuinely reflects the real current git state — run in a real subprocess against this actual repo, confirm it matches `git rev-parse HEAD`'s own output at test time (same "prove it's real, not a fixed string" discipline as prior PRDs' wire-is-real tests).
- [ ] Rejection test: a `HardwareDeclaration` with a nonsensical value (negative `cpu_cores`, etc.) fails loudly at construction — same validate-at-the-boundary pattern as `shared/config.py`.

## 5. Scent-map commitment — extending, not reopening, the frozen `State` spec

- [ ] Per PRD DQ5: add `integrity/scent_commitment.py` (or fold into `commit_reveal.py` if it stays small — check the 150-line cap before splitting) — `commit_scent_map(scent_data: dict[Position, float]) -> str`: serializes via `tools/scent_wire.py::serialize_scent_field` (already the canonical wire form), then canonical-JSON + SHA-256, same pattern as everything else here.
- [ ] `integrity/audit.py::verify_scent_map_against_commit(claimed_field: dict[Position, float], commit_hash: str) -> bool` — **the exact API `test_prd6_scent_audit_guard.py` already names**; re-serializes `claimed_field` via the same `serialize_scent_field` path and compares hashes (`secrets.compare_digest`), never compares floats directly.
- [ ] Wire the commitment into `orchestrator_peer.py`'s flow: when `share_scent_map()` is about to respond, also compute and log (or return alongside) that turn's scent-map commitment hash — decide exactly where this hash needs to travel (does the *receiver* need it upfront to later verify, or is it purely a final-audit-time reconstruction from the trace log? Recommend: log it in the sender's own trace at `share_scent_map` time, matching how every other integrity fact in this repo already lives in the trace log for later audit, not a new real-time channel).
- [ ] Run the exact guard test (`test_prd6_scent_audit_guard.py`) — confirm it now XPASSes with `strict=True`, meaning it hard-fails the suite if left in place. **Delete it in the same commit**, per the file's own stated discipline.
- [ ] New test replacing the deleted guard: a real `ScentField.full_field()` snapshot, committed then verified — both the honest-path accept and a tampered-field reject, matching this project's "write at least one test per layer that proves rejection" rule (the old guard only ever tested the reject path with a placeholder hash; the real implementation needs the honest-path accept test too).

## 6. `integrity/capture_protocol.py`

- [ ] `CaptureClaim` dataclass: `thief_pos: Position`, `cop_pos: Position`, `claimed_at_step: int` (or similar — decide what's needed for the claim to be auditable against a specific commit later).
- [ ] `CaptureResponse` dataclass: `confirmed: bool`, `true_thief_pos: Position` — **the exact API `test_prd6_missing_wire_channels_guard.py` already names** (`response.confirmed`).
- [ ] `claim_capture(thief_pos: Position, cop_pos: Position) -> CaptureClaim`: pure, local, honest-by-construction (this repo only ever calls it when `domain/capture.py`'s own `is_coordinate_capture`/`is_barrier_capture` already returned `True` locally — the claim function itself doesn't re-derive that, it just packages an already-true local fact).
- [ ] `respond_to_capture_claim(claim: CaptureClaim, true_thief_pos: Position) -> CaptureResponse`: `confirmed = (claim.thief_pos == true_thief_pos)`. This repo is the cop — in practice this function is called on data *this repo receives from the thief peer* (the thief is the one who can truthfully confirm/deny, since only the thief knows its own real position) — document this asymmetry explicitly in the module docstring: the cop only ever *sends* claims, the thief-repo's own equivalent function is what actually calls `respond_to_capture_claim` for real; this repo builds and tests both directions since rules 21/22 are symmetric and the guard test exercises both, but only one direction is this repo's own live call path.
- [ ] Test: `claim_capture` then `respond_to_capture_claim` with matching positions → `confirmed=True` (the exact guard test scenario, now for real).
- [ ] Rejection test: mismatched positions → `confirmed=False` — the new test the old guard never had room to write (it only tested the accept path).
- [ ] Both claim and response fold into that side's own next commit envelope — wire this: extend `CommitEnvelope`'s `move`/a new field to optionally carry a pending capture claim/response, OR keep it as a separate hash committed alongside (decide, document the choice, matching DQ6's "same machinery" principle without necessarily cramming it into the exact same 7-field envelope if that distorts `move`'s own meaning).

## 7. Wire tools — `tools/mcp_server.py` / `mcp_client.py`

- [ ] `receive_commit(h_commit: str) -> dict`: accepts a peer's commit hash for this turn, returns `{"acknowledged": True}` — satisfies ch. 5.3.2's Commit+Acknowledge steps in one synchronous MCP round-trip (PRD DQ4's own resolution: Acknowledge is the existing ack, not a separate state/tool).
- [ ] `receive_reveal(move: dict, hint_text: str) -> dict`: the Step 3 payload — **no nonce parameter** (PRD DQ2: nonce stays hidden here). Returns an ack confirming receipt, same shape discipline as `receive_hint` today.
- [ ] `receive_final_reveal(nonces: dict) -> dict`: end-of-game only — all of this side's own nonces for the whole game, keyed by step number. Triggers (or makes available for) `integrity/audit.py`'s full replay.
- [ ] `receive_barrier_declaration(target: dict) -> dict`: `{"col": int, "row": int}` — the actual barrier position, legally disclosed per rule 15. Sent the same turn a barrier is placed, alongside (not instead of) that turn's commit.
- [ ] `receive_capture_claim(claim: dict) -> dict` / `receive_capture_response(response: dict) -> dict`: wire shapes for `capture_protocol.py`'s dataclasses, serialized.
- [ ] Update `build_server()`'s signature: new `on_commit`/`on_reveal`/`on_final_reveal`/`on_barrier_declaration`/`on_capture_claim`/`on_capture_response` callback parameters, same injected-callback pattern every existing tool already uses (`tools/` stays a thin transport layer, rule 3/I2).
- [ ] Corresponding `mcp_client.py` functions: `send_commit`, `send_reveal`, `send_final_reveal`, `send_barrier_declaration`, `send_capture_claim`, `send_capture_response`.
- [ ] Decide and document: does `receive_hint`/`share_scent_map` (PRD 4 Revision 3's existing tools) get *replaced* by `receive_reveal`, or do they stay as-is with `receive_reveal` wrapping/superseding them at the orchestration level? Recommend: `receive_hint` is subsumed by `receive_reveal`'s `hint_text` field — one fewer tool overall, not two overlapping ones; `share_scent_map` stays independent (it's a pull-based data query, not part of the commit-reveal claim cycle at all, per PRD 4's own architecture — only its *commitment hash* is new, per §5).
- [ ] Full test rebuild for every test currently calling `receive_hint`/`send_hint` directly — this touches `test_mcp_server.py`, `test_mcp_client.py`, `test_orchestrator*.py`, the integration tests — budget significant time, this is the biggest test-surface change in the whole layer.
- [ ] "Grep the wire" sweep, PRD 4's own discipline reapplied: confirm `receive_barrier_declaration`'s payload and every other new tool's payload never accidentally carries something rule 27 forbids beyond what's explicitly legally required (barrier positions, rule 15) — no stray coordinate leaking through `receive_reveal`'s `move` field beyond a legitimate direction string or (legally-required) barrier target.

## 8. `Orchestrator`/`orchestrator_turn.py`/`orchestrator_peer.py` wiring

- [ ] `take_turn()` restructured around the new cycle: compute move → build `CommitEnvelope` → `commit()` → `send_commit` (get ack) → `send_reveal` (move + hint_text, no nonce) → (if a barrier was placed) `send_barrier_declaration` → (if a capture was claimed) `send_capture_claim`/handle response.
- [ ] Nonce storage: each turn's nonce must be retained locally (never transmitted early) until `receive_final_reveal` time — decide where this lives (`Orchestrator` gains a `self._nonces_by_step: dict[int, str]` or similar), and confirm it's genuinely never serialized into the trace log in a way that would leak it before game end (the *operational* trace log, `observability/trace.py`, is a different, non-cryptographic artifact — confirm nonces don't accidentally end up in it prematurely; if they do for debugging convenience, that's a real rule 18 violation risk worth an explicit test).
- [ ] Test: a full round — two real `Orchestrator` instances, one commits+reveals a move, the other receives and acks/stores it — end to end, matching every prior PRD's own "one real round-trip" milestone discipline.
- [ ] Test: nonce is provably absent from every wire payload up to (not including) the final-reveal call — inspect the actual bytes sent at `send_commit`/`send_reveal` time.

## 9. `integrity/audit.py` — the mutual audit engine

- [ ] `AuditResult` dataclass: `passed: bool`, `mismatches: list[...]` (or similar — enough detail to explain *why* a failure happened, not just that one did).
- [ ] `run_mutual_audit(trace_log_path, nonces: dict[int, str]) -> AuditResult`: reads the full trace log, reconstructs each turn's `CommitEnvelope` from logged facts (move, intent, hint_text, step, role, state at that point) plus the now-revealed nonce, recomputes `Hcommit` via `commit_reveal.commit()`, compares against the `Hcommit` that was actually logged as sent that turn — any mismatch anywhere fails the whole audit (rule 19, no partial credit).
- [ ] The **adversarial milestone**: construct a log where one turn's committed `Hcommit` doesn't match what the (now-revealed) fields recompute to — confirm `run_mutual_audit` catches it. This is the single most important test in this entire PRD, matching the project's own repeated "a verifier that never rejects anything is worthless" rule — do not skip or under-invest in this test.
- [ ] Honest-path test: a real, un-tampered two-Orchestrator exchange (§8's round-trip), full final-reveal, audit passes cleanly.
- [ ] Wire `verify_scent_map_against_commit` (§5) into the same audit pass — a tampered scent-map commitment should also fail the overall audit, not just its own isolated unit test.
- [ ] `run_mutual_audit` becomes the foundation PRD 7's Replay/verifier app (rule 20) will call — note this explicitly in the module docstring so PRD 7 doesn't rebuild audit logic that already exists here.

## 10. Config identity gate

- [ ] A small, explicit step (function or documented manual procedure — decide which, per PRD DQ3's own "administrative, not a wire tool" resolution) that runs `check_config.py --identical` as a *precondition* recorded in `Step0Declaration.config_sha256`, not just a standalone CLI a human might forget.
- [ ] Test: `Step0Declaration` construction fails loudly (or is flagged) if the local config's own SHA-256 doesn't match what `check_config.py` computes independently — a consistency check between this layer's own hash computation and the existing skill script's, since they must agree.

## 11. Cleanup and final verification

- [ ] Delete `tests/unit/test_prd6_missing_wire_channels_guard.py`'s xfail markers (or the whole file, if nothing in it is worth keeping as a real test) — confirmed XPASS first, per `strict=True`'s own enforcement.
- [ ] Delete `tests/unit/test_prd6_scent_audit_guard.py` the same way.
- [ ] Remove `RULE-15-16-BARRIER-DECLARATION-AT-PRD-6`, `RULE-21-22-CAPTURE-CLAIM-AT-PRD-6`, `RULE-19-SCENT-AUDIT-AT-PRD-6` marker comments from `domain/barriers.py`, `domain/capture.py`, `orchestrator_turn.py` — `grep -rn` for all three returns nothing when done.
- [ ] `scripts/watch_prd6_commit_reveal.py` — a live demo script, same discipline as every prior PRD: local commit/verify round-trip, one real two-process commit+reveal exchange, Step-0 declaration printed, and the adversarial audit-rejects-tampering case shown live, not just asserted in a test.
- [ ] Full `uv run pytest` — green, 100% coverage.
- [ ] `uv run ruff check .` — clean.
- [ ] `check_config.py` — still passing, unaffected by this layer's own code (it doesn't touch the config file itself).
- [ ] Every new/touched module re-checked against the 150-line house cap — this layer adds more new files than any prior PRD; budget real attention here, several are likely to need splitting on the first pass.
- [ ] `rule-auditor` run against the full rule set this layer owns (11, 12, 15, 16, 17, 18, 19, 21, 22, 23, 24, 53) — explicit sign-off gate before commit, same discipline as the full-fix pass's own §C7 precedent, given how fatal-rule-dense this layer is.
- [ ] Sanity-check sabotage, at minimum: (a) tamper one committed field before final reveal, confirm the audit test built in §9 actually catches it (already required there, re-confirm as part of final sweep); (b) temporarily make `verify()` use `==` instead of `secrets.compare_digest`, confirm nothing currently distinguishes this (timing-attack resistance can't be unit-tested directly, but confirm the *code review* — read the diff — shows the right primitive is used, and revert immediately regardless of what the sabotage "proves," since this one is about code inspection, not test outcomes).
- [ ] Update `PRD-6-security-and-cryptography.md`'s status line to "Built & verified" with an honest retrospective section, same as every prior PRD's own closing discipline — note anything found via construction that wasn't anticipated here.
- [ ] Update `TODO.md`'s own PRD 6 entry.
- [ ] `WIRE-CONTRACT.md` gets a real update — this layer adds the largest wire-surface change yet (six new tools); send it to the teammate as a new proposal, not a formality, matching the discipline already established for PRD 4 Revision 3.
- [ ] Commit only after all of the above — matching every prior layer's own closing rule.
