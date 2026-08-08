# PRD 9 — Step-0 negotiation ceremony

Status: **Built & verified.** 455 unit tests + 8 integration tests, 99% coverage on `src/cop`, `ruff check .` clean, `check_config.py` passing, two full watched runs (`scripts/watch_prd9_step0_negotiation.py`) — a genuine mutual lock, and a clean, mutually-visible `TECHNICAL_LOSS` on a real config mismatch. `rule-auditor`, scoped to rules 5/9/11/18/19/23/24/49, found one real gap after the first build pass — fixed before this status line was written, not left open (Retrospective, below).

Triggered by `cop-team-fix-list.md` (the Thief side's own review, grounded against the book directly and against this repo's `RULES.md`), not by a new rule reading — it flagged four gaps, all confirmed by reading the actual current code before this PRD started: rule 23 **[FATAL]** (no scent-model cryptographic lock), rule 11 **[FATAL]**'s real enforcement point (`verify_config_identity()` built, never called from anywhere), rule 49 (no channel for the opponent's own repo URLs, hand-supplied and easy to get wrong), and no live Step-0/negotiate exchange tool at all. All four turned out to share one root cause: `Step0Declaration`/`verify_config_identity` (`integrity/step0.py`) existed and were unit-tested in isolation, but nothing ever put them on the wire or called them automatically before a match starts — the same shape of gap PRD 8 closed for the capture-claim protocol and the end-of-game sequence.

## The three things this closes

1. **A cryptographic scent-model lock** (rule 23) — `Step0Declaration` gains `scent_model_sha256` (`integrity/scent_model_lock.py`), a SHA-256 of the fixed formula shape (ch. 4.3/Figure 4) plus this series' configured numbers plus a worked numeric example computed by actually running `ScentField.advance()` — not hand-typed, so it can't drift from the real implementation.
2. **A live, automatic Step-0 exchange** (rule 11's real enforcement, rule 24) — one new MCP tool, `receive_step0`, and `orchestrator_step0.py::negotiate_step0`/`_on_step0_received`. Both sides independently verify the peer's `config_sha256` and `scent_model_sha256` against their own locally computed values (`secrets.compare_digest`) before any turn is played — a mismatch is a clean, logged `TECHNICAL_LOSS`, not a silent continue and not something caught only at final audit.
3. **A negotiated channel for the opponent's repo URLs** (rule 49) — `repos` rides alongside the signed declaration in the same `receive_step0` call. `report_game()` now sources `opponent_cop_repo_url`/`opponent_thief_repo_url` from `self._opponent_repos` (set by a completed negotiation) when not explicitly overridden.

## Build

- **`src/cop/integrity/scent_model_lock.py`** (new) — `compute_scent_model_hash(config) -> str`. The worked numeric example runs `ScentField.advance()` twice on an oversized synthetic board (so the kernel never clips), reproducing `WIRE-CONTRACT.md`'s own documented 0.9 → 0.81 example exactly under the default Table 16 numbers.
- **`src/cop/integrity/step0.py`** — `Step0Declaration` gains `scent_model_sha256: str` (non-empty-string validated, folded into the signed canonical bytes, same discipline `config_sha256` already used).
- **`src/cop/integrity/step0_wire.py`** (new) — `declaration_to_wire`/`declaration_from_wire`, split out of `orchestrator_step0.py` once that file grew past the 150-line cap. Rule 9: a malformed incoming shape raises `KeyError`/`TypeError`/`ValueError`, never crashes uncaught.
- **`src/cop/planner/state_machine.py`** — `NEGOTIATING` added as a legal state, `{WAITING_FOR_OPPONENT, TECHNICAL_LOSS}` — **not** the dataclass's own default (see Design Question 1).
- **`src/cop/tools/mcp_server_prd9.py` / `mcp_client_prd9.py`** (new) — `receive_step0`/`send_step0`, one synchronous round trip (see Design Question 2). Wired into `mcp_server.py::build_server` via a new `on_step0` callback parameter.
- **`src/cop/orchestrator_step0.py`** (new mixin, `Step0NegotiationMixin`) — `_build_own_step0`, `_verify_peer_step0` (the one check both directions run), `_on_step0_received` (responder), `negotiate_step0` (initiator). `Orchestrator.__init__` gains `shared_config_path` (a new constructor parameter — the shared config's own path was never tracked anywhere on the instance before this was needed) and `self._opponent_repos: dict[str, str] | None`.
- **`src/cop/orchestrator_end_of_game.py::report_game`** — `opponent_cop_repo_url`/`opponent_thief_repo_url` become optional, sourced from `self._opponent_repos` via a new `_opponent_repo_url` helper when omitted; raises `ValueError` if neither an override nor a completed negotiation is available.
- **`scripts/watch_prd9_step0_negotiation.py`** (new demo) — two real `Orchestrator`s, a genuine successful negotiation and an adversarial single-tampered-byte config mismatch, both run and watched.

## Milestone

Two real `Orchestrator`s, one calling `negotiate_step0()` against the other's real HTTP server. Case 1: both sides' `config_sha256`/`scent_model_sha256` genuinely agree — negotiation succeeds, both state machines independently reach `WAITING_FOR_OPPONENT`, and each side prints the other's real repo URLs, learned from the wire, not hand-supplied. Case 2: one side's shared config file is tampered by a single trailing byte — `negotiate_step0` raises `Step0MismatchError`, and **both** state machines (initiator and responder) independently reach `TECHNICAL_LOSS` — not a hang, not a one-sided failure invisible to the other side.

## Design questions answered here

**1. Should `NEGOTIATING` be the state machine's new default/initial state?** No — checked against the actual blast radius first: `Orchestrator.__init__` constructs `PeerStateMachine()` once, and dozens of PRD 1-8 tests construct an `Orchestrator` and immediately drive the per-turn cycle assuming it starts at `WAITING_FOR_OPPONENT`. Changing the default would have forced every one of those call sites to explicitly reset state first, for no benefit — the negotiation ceremony is a real, once-per-match event, not something every `Orchestrator` instance needs to pass through. Instead, `negotiate_step0` and `_on_step0_received` each explicitly construct `PeerStateMachine(state="NEGOTIATING")` themselves, at the moment the ceremony actually begins for that side — `WAITING_FOR_OPPONENT` stays the dataclass's own unchanged default for every other caller.

**2. Why one synchronous round trip instead of PRD 6's split commit/callback shape?** Ch. 5.5 gives no reason for asynchrony: unlike a per-turn commit (which must wait for the *opponent's own future move*), both sides already hold everything Step-0 needs — hardware, code hash, locally-computed hashes — the instant the call arrives. A second tool and a wait-for-event primitive would add real complexity (another `asyncio.Event`, another deadline wrapper) to buy nothing.

**3. Why do both sides verify independently rather than trusting the initiator's check alone?** Rule 9 — everything a peer sends is untrusted — applies in both directions, not just to whoever happens to call first. A responder that blindly echoed its own declaration back without checking the initiator's could end up in a broken, unverified state invisible to itself even if the initiator's own check (symmetric, against the same two hashes) would have caught the same mismatch from its side. Both `negotiate_step0` and `_on_step0_received` call the identical `_verify_peer_step0`.

**4. What about the missing `-m cop peer` CLI?** `CLAUDE.md` documents `uv run python -m cop peer` as this repo's own run command, but no `__main__.py` exists anywhere in `src/cop` — confirmed by search before this PRD started, a real, pre-existing gap. **Explicitly out of scope here, by direct user decision**: `negotiate_step0()` ships as a real method plus a watched demo script, the same precedent `report_game()` set in PRD 8 (`play_game`/`report_game` also have no CLI caller yet) — not folded into a new CLI in the same pass.

## Also verify (acceptance criteria, checked once built)

- A config mismatch is caught **before** any turn is played, not only at final audit — `negotiate_step0` itself raises, it does not require a full match to run first.
- The scent-model lock is a real, independent check, not a restatement of `config_sha256` — a config with byte-identical files but a monkeypatched `scent_decay_rate` in the object actually driving `ScentField` is still rejected.
- A forged/tampered signature is rejected even when both sides' underlying config and scent-model hashes agree — the signature check runs first and independently.
- `report_game()`'s explicit `opponent_cop_repo_url`/`opponent_thief_repo_url` parameters still override a completed negotiation when supplied — the negotiated value is a default, not the only path.

## New dependency

None — every piece (`secrets.compare_digest`, `hashlib`, `asyncio`, `ScentField`, `PeerStateMachine`, FastMCP) already exists in this repo or the stdlib.

## Builds on

PRD 6's `integrity/step0.py`/`integrity/canonical_json.py` (extended, not reopened — `config_sha256`'s own discipline is exactly copied for `scent_model_sha256`). PRD 4's `memory/scent.py::ScentField` (reused to compute the worked example, not reimplemented). PRD 8's "separate, explicit call" precedent for `report_game()` (`negotiate_step0` follows the identical shape). PRD 2's `planner/deadline.py::await_with_deadline` (network failure during negotiation reaches `TECHNICAL_LOSS` the same way every other peer call already does).

## Explicitly out of scope

The missing `-m cop peer` CLI entry point (Design Question 4). All four Table 20 report files beyond `result_<game_id>.json` (pre-existing PRD 8 scope boundary, untouched here). Cross-sub-game cumulative score tracking (pre-existing PRD 8 scope boundary, untouched here).

## Retrospective

`rule-auditor` (scoped to rules 5, 9, 11, 18, 19, 23, 24, 49) found one real, non-fatal gap in the first build: `repos` (rule 49) reached `self._opponent_repos` with no shape validation at all — `_on_step0_received`/`negotiate_step0` did `self._opponent_repos = dict(repos)` unconditionally. A peer sending a malformed shape (a missing `"cop"`/`"thief"` key, a non-string value) would have surfaced as an uncaught `KeyError` inside `report_game()` at the end of a real match, not the clean `Step0MismatchError`/`TECHNICAL_LOSS` path every other malformed-peer-input case in this layer already gets — a real rule-9 gap (untrusted peer data reaching instance state unchecked), even though `repos` itself is deliberately outside the signed hash (WIRE-CONTRACT.md's own documented tradeoff, unchanged by this fix).

**Fixed, not left open:** `integrity/step0_wire.py::validate_repos()` (new) — a peer's `repos` dict must have exactly the two keys `("cop", "thief")`, both non-empty strings, or raises `ValueError`. `_verify_peer_step0` now validates `repos` in the same pass as the declaration itself (same `try/except (KeyError, TypeError, ValueError)` block, same `Step0MismatchError` path), returning `(declaration, validated_repos)` — both `_on_step0_received` and `negotiate_step0` now only ever store a shape-checked `dict[str, str]` into `self._opponent_repos`. Two new rejection tests (`test_verify_peer_step0_rejects_a_repos_payload_missing_a_required_key`, `test_verify_peer_step0_rejects_a_non_string_repos_value`). The audit's second observation — `verify_config_identity()` stays dead code, since `_verify_peer_step0` reimplements the same `hash_config_file` + `compare_digest` check inline rather than calling it — was read and accepted as accurate but not changed: the *outcome* rule 11 requires is achieved either way, and `verify_config_identity`'s own two-local-file-path signature doesn't fit the live-wire call shape without a pointless indirection. `_check_hash()` was extracted while fixing the `repos` gap to keep `orchestrator_step0.py` under the 150-line cap once the new validation branch landed — a byproduct of the fix, not a separate motivation.
