# TODO15 — Build Checklist for PRD 15 (Deadline Tracker & Watchdog Reliability Hardening)

Status: **Built & verified.** Read `PRD/PRD-15-reliability-tracker-hardening.md` in full first — it records four decisions (two real fixes, two deliberate non-fixes with reasoning) and a fifth item: a pre-existing, test-suite-only watchdog-thread hazard, confirmed via `git stash` against the clean tree, found during this PRD's own verification and fixed within rule 7's constraints (§6 below) rather than left as a follow-up.

## 1. `src/cop/planner/deadline.py` — `now_and_deadline`

- [x] `now_and_deadline(timeout_seconds) -> (sent_at, deadline_at)` — one shared computation (I6), not repeated per call site.
- [x] Tests: `deadline_at` is exactly `timeout_seconds` after `sent_at`; `sent_at` is a real current timestamp (bounded by `time.time()` calls immediately before/after).

## 2. Wire-level timing on the Commit-Reveal round trip

- [x] Investigated `fastmcp.Client.call_tool`'s own `meta`/`timeout` params before committing to an approach — no existing precedent anywhere in this repo for reading FastMCP `Context` metadata server-side, so went with explicit typed kwargs (consistent with every other tool in `mcp_server_prd6.py`) rather than chasing unconfirmed framework internals.
- [x] `tools/mcp_client_prd6.py::send_commit`/`send_reveal` — gained required `sent_at: float, deadline_at: float`, both threaded into the `call_tool` payload.
- [x] `tools/mcp_server_prd6.py::receive_commit`/`receive_reveal` — gained the matching required params, passed through to `on_commit`/`on_reveal`.
- [x] `orchestrator_commit_reveal.py::commit_and_reveal_to_peer` — computes `now_and_deadline(...)` immediately before each of the two sends.
- [x] `orchestrator_peer_audit.py::_on_commit_received` / `orchestrator_turn.py::_on_reveal_received` — both gained `sent_at`/`deadline_at` params, log them as `peer_sent_at`/`peer_deadline_at` on the existing `peer_commit_received`/`hint_received` trace events.
- [x] `orchestrator_peer_audit.py::_log_if_peer_deadline_already_expired` — shared helper (both mixins compose into the same `Orchestrator`), logs one informational `peer_declared_deadline_already_expired` event when a peer's own declared deadline has already passed on receipt. Rule 9: observational only, never affects this side's own `await_with_deadline` bound.

## 3. Tests for wire-level timing

- [x] `test_orchestrator_commit_reveal.py::test_a_real_round_trip_carries_the_senders_declared_timing_to_the_receiver` — a real client→server round trip, asserts the receiver's trace log has both `peer_commit_received` and `hint_received` carrying `peer_sent_at`/`peer_deadline_at` matching `config.response_timeout_seconds`.
- [x] `test_a_deadline_already_expired_on_receipt_logs_an_informational_event_only` / `test_a_deadline_still_in_the_future_on_receipt_logs_nothing_extra` — both branches of `_log_if_peer_deadline_already_expired`, not just the happy path (house rule: prove rejection/the edge case too).
- [x] Every fake test-peer across the suite that registers its own `receive_commit`/`receive_reveal` tool (8 files, ~11 occurrences) updated to accept the two new required fields — found via running the full suite and fixing each real `ToolError`/`unexpected_keyword_argument` failure, not by guessing which files needed it.
- [x] Two `scripts/watch_prd*.py` demo scripts (`watch_prd8_live_match.py`, `watch_prd5_tunnel.py`) also updated for consistency, though not covered by the automated suite.

## 4. `src/cop/orchestrator_server.py` — real structured Watchdog snapshot

- [x] `ServerLifecycleMixin._persist_watchdog_state` — logs `own_pos`/`target_pos`/`barriers_placed`/`steps_taken` alongside the existing phase string. `barriers_placed` built as `sorted([p.col, p.row] for p in ...)` — `Position` has no `__lt__`, so sorting bare `Position` objects would raise `TypeError`.
- [x] `orchestrator.py::__init__` — `Watchdog(persist_state=self._persist_watchdog_state, ...)`, replacing the old one-line-phase-only lambda.
- [x] Test: `test_orchestrator_watchdog.py::test_watchdog_persist_state_snapshots_real_live_game_state_not_just_the_phase` — sets up genuinely non-default `own_pos`/`target_pos`/barriers/`steps_taken` first (not defaults, so the test can't pass by coincidence), forces staleness, asserts the snapshot's real fields.

## 5. Documentation

- [x] `PRD/PRD-15-reliability-tracker-hardening.md` — the design doc: what was found, what was fixed, what was deliberately not fixed and why, plus the leaked-watchdog-thread finding and its own fix.
- [x] `README.md` §5 — fifth documented-contradiction note (the no-retry decision), matching the existing four-note pattern exactly as specified.

## 6. Leaked watchdog-monitor thread — found during verification, fixed within rule 7's constraints

- [x] Root-caused: `_watch_loop`'s daemon thread (started by every `run_as_server` call) called the real `os._exit(1)` once `watchdog_threshold_seconds` (60s) elapsed since its orchestrator's last heartbeat — harmless in production (one orchestrator per process, thread dies with the process, rule 1/2), but a shared pytest process accumulates hundreds of orchestrators across a session, so an early test's abandoned thread could eventually kill the whole suite.
- [x] Confirmed pre-existing and unrelated to any of this session's other changes via `git stash` against the clean tree (reproduced identically).
- [x] `orchestrator_server.py::_watch_loop` — `time.sleep` replaced with `self._watchdog_stop_event.wait(poll_interval_seconds)`; doubles as the poll delay and an interruptible stop signal.
- [x] `orchestrator_server.py::stop_watchdog_monitor()` — sets the event. Idempotent; a real deployed peer never needs to call it (rule 7 stays intact — a *live* match's watchdog is untouched, this only matters for an orchestrator that's genuinely done).
- [x] `orchestrator.py::_init_cross_thread_signals` — `self._watchdog_stop_event = threading.Event()`.
- [x] `tests/conftest.py::_stop_watchdog_monitors_after_test` — autouse fixture, tracks every `Orchestrator` constructed during one test (scoped `patch.object` on `__init__`, not a permanent production registry) and calls `stop_watchdog_monitor()` on each at teardown.
- [x] `test_orchestrator_watchdog.py::test_stop_watchdog_monitor_actually_stops_the_background_poll_loop` — proves `stop_watchdog_monitor()` itself: forces staleness *after* stopping, asserts `os._exit` never fires.
- [x] The old manual `heartbeat()`-before-return workaround in `test_run_as_server_starts_a_watchdog_monitor_that_shuts_down_on_staleness` removed — the conftest fixture now handles it centrally.
- [x] **Verified end to end**: full `tests/unit` run, previously dying partway through every time, now completes cleanly — 740 passed, 356s, no premature termination.
- [x] Found (and fixed) a real side effect of `_persist_watchdog_state` itself: `test_prd4_seam.py`'s AST guard test matched *any* `target_pos=` keyword by name, including the new unrelated `trace.log(..., target_pos=[...], ...)` call — narrowed the scan to `GameState(...)` calls specifically, its actual documented intent.

## 7. Explicitly out of scope (follow-ups, not required for this PRD's milestone)

- [ ] Extend `sent_at`/`deadline_at` to `send_barrier_declaration`/`receive_barrier_declaration`, `send_capture_claim`/`receive_capture_claim`, `send_capture_response`/`receive_capture_response`, and `mcp_server_prd9.py`'s Step-0 tools — identical shape to §2 above, just more call sites.
- [ ] A full match auto-resume protocol reading `watchdog_persist_state`'s snapshot back — a materially larger feature (new state-machine states, a resume negotiation step, peer-side cooperation), deliberately left for a future PRD if ever needed.

## Also verify

```bash
uv run pytest tests/unit/test_deadline.py tests/unit/test_orchestrator_commit_reveal.py tests/unit/test_orchestrator_watchdog.py tests/unit/test_mcp_server_prd6.py tests/unit/test_mcp_server.py tests/unit/test_mcp_client.py tests/unit/test_prd4_seam.py -q
uv run ruff check src/cop/planner/ src/cop/tools/ src/cop/orchestrator.py src/cop/orchestrator_server.py src/cop/orchestrator_turn.py src/cop/orchestrator_commit_reveal.py src/cop/orchestrator_peer_audit.py tests/conftest.py
wc -l src/cop/planner/deadline.py src/cop/tools/mcp_client_prd6.py src/cop/tools/mcp_server_prd6.py src/cop/orchestrator.py src/cop/orchestrator_server.py src/cop/orchestrator_turn.py src/cop/orchestrator_commit_reveal.py src/cop/orchestrator_peer_audit.py   # all ≤150
python .claude/skills/spec-guard/scripts/check_config.py config/shared/config_dev_g01.json
uv run pytest tests/unit -q   # full suite: completes cleanly, no premature os._exit
```
