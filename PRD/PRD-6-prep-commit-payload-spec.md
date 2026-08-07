# PRD 6 prep — commit payload spec (frozen before PRD 6's hashing code exists)

Not PRD 6 itself. PRD 6 (Commit-Reveal over SHA-256, per `PLAN.md`) hasn't been designed yet — this document exists to answer one question in writing, before any hashing code gets written, per the standing project discipline of deciding design questions on paper rather than guessing at code time (see every prior PRD's own "Design questions answered here" section).

**The question:** exactly which fields enter `SHA256(State ‖ Move ‖ Intent ‖ Nonce)`?

**Why this can't wait for PRD 6 itself:** the book's Commit-Reveal formalism names `State` as one of the four hashed components, and this repo already has a `State` object (`reasoning/state.py::GameState`) that PRD 6 will almost certainly reach for. `GameState` itself carries no floats today — but `Orchestrator` also owns a `scent_field: ScentField` and `belief_map: BeliefMap`, both genuinely full of floats (Table 16's decay arithmetic, `_HINT_BOOST`/`_SCENT_REPORT_BOOST` reweighting), and "State" is exactly the kind of word a PRD 6 implementer reaches for `self.scent_field`/`self.belief_map` under, six months from now, without re-deriving this reasoning from scratch. Two peers computing the same logical float (`0.1 + 0.2`) through different code paths — different Python versions, different operation orderings, different accumulated rounding — can serialize `0.30000000000000004` on one side and `0.3` on the other. Canonical JSON (`sort_keys=True, separators=(",", ":")`, already mandated in `PLAN.md`'s PRD 6 "Also verify" line) makes the *key order* deterministic; it does nothing for float representation. Every honest game fails its own audit, both sides score zero, rule 19 has no mercy for "but the numbers were actually equal."

## The frozen field list

**State** (this agent's own committed facts — never a belief, never inference apparatus):

| Field | Type | Source | Why included |
|---|---|---|---|
| `own_pos` | `[col: int, row: int]` | `GameState.own_pos` | the fact being committed to — where this agent's move started from |
| `steps_taken` | `int` | `GameState.steps_taken` | binds the commit to a specific turn (see the companion step-index test, `tests/unit/test_step_index_agreement.py`) |
| `barriers_placed` | sorted list of `[col, row]` pairs | `GameState.barriers.placed` | rule 15/16's eventual declaration payload — sorted explicitly (see "Ordering, not just floats" below), not emitted in `set` iteration order |

**Explicitly excluded from State, and why:**

- `target_pos` — this is *belief*, not truth (PRD 4 Design Question 2/4). Committing to a belief would mean committing to something that can legitimately change turn to turn based on unverifiable inference; a peer auditing the log has no way to check a belief against anything. Only facts about the committer's own position/actions belong in a cryptographic commitment.
- `scent_field` / `belief_map` — the trap this document exists to name. Both are internal inference apparatus (Table 16 decay arithmetic, multiplicative reweighting), entirely local, never any peer's business to verify, and both are dense with floats. Rule 23's own scope (lock the *emission model*, i.e. the formula and its config parameters) is already satisfied by `check_config.py` validating `scent_source_strength`/`scent_decay_rate`/`scent_field_size` — it does not require or benefit from hashing live scent *values* into a per-turn commit.

**Move** — already float-free by construction: `{"type": "move", "direction": str}` (one of `domain.movement.DELTAS`' keys) or `{"type": "barrier", "target": [col: int, row: int]}` (`reasoning.brain_base.Move`/`PlaceBarrier`).

**Intent** — `bool`. Already generated and locally recorded per-turn (`orchestrator_turn.py`'s `trace.log("hint_generated", intent=...)`, PRD 4's own "Explicitly out of scope" promise) — PRD 6 reveals it, doesn't need to reshape it.

**Nonce** — hex string from `secrets.token_hex`, per `PLAN.md`'s own mandate (rule 18: never `random`). Already a string; no float risk.

## Ordering, not just floats

`GameState.barriers.placed` is a Python `set[Position]`. Two independently-constructed `BarrierSet`s holding the *same logical barriers*, built by inserting them in a *different order* (exactly what happens between two peers who placed barriers across different turns, or the same peer reconstructing state from a replayed log), are not guaranteed to iterate in the same order — `json.dumps(list(a_set), sort_keys=True, ...)` only sorts *dict keys*, not the *contents of a list*. `sort_keys=True` alone does not protect a set-turned-list value. The canonical serializer below sorts the barrier list explicitly, by `(col, row)`, before it ever reaches `json.dumps`.

(Investigated whether this is even a live risk given `Position`'s hash: since `Position(col, row)`'s dataclass-generated `__hash__` derives from `hash((col, row))`, and Python does not salt integer hashes with `PYTHONHASHSEED` — only `str`/`bytes` — the *specific* hash-randomization risk this project has been careful about elsewhere (nonce/string hashing) does not actually apply to `Position` sets today. Sorting explicitly regardless: relying on "this particular hash implementation detail happens to be stable" is exactly the kind of unstated assumption this document exists to close off, and integer-hash stability is a CPython implementation detail, not a language guarantee.)

## The frozen serializer

`src/cop/integrity/commit_payload.py::canonical_state_bytes(game_state: GameState) -> bytes` — deliberately built *now*, not deferred to PRD 6, so the spec above is enforced in code rather than staying a document nobody re-reads. Extracts exactly the three fields above, sorts the barrier list, serializes via `json.dumps(..., sort_keys=True, separators=(",", ":"))` (`PLAN.md`'s own mandated canonical form), encodes UTF-8. Walks the payload recursively first and raises `TypeError` on any `float` value found anywhere in it — an active, code-enforced version of "if a float has to be in there, fix the precision as a string at the boundary," not just a sentence in this document that erodes the first time someone doesn't re-read it.

`Move`/`Intent`/`Nonce` are not given the same treatment here: they're primitives (a direction string, a two-field dict of ints, a bool, a hex string) with no float/ordering risk to defend against, and their exact shape depends on PRD 6 decisions (the four-phase exchange envelope) this document isn't trying to pre-empt. Only `State` — the part that reaches into `Orchestrator`'s existing float-bearing objects if built carelessly — gets frozen this early.

## Verification

`tests/unit/test_commit_payload_spec.py`: constructs the same logical `GameState` (same position, same step count, same barrier set) via several different code paths — barriers inserted in different orders, the `GameState` built via different construction sequences — several hundred times, and asserts `canonical_state_bytes` produces byte-identical output every time. Separately confirms the float guard actually fires (temporarily smuggling a float into a test-only payload variant and confirming `TypeError`), and that varying `PYTHONHASHSEED` across real subprocess runs doesn't change the output (the one part of "ordering, not just floats" that's worth confirming empirically rather than reasoning about from CPython internals alone).
