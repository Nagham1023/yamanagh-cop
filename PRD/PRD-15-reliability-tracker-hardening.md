# PRD 15 — Deadline Tracker & Watchdog reliability hardening

## The gap this closes

A spec-compliance pass (this session) checked ch. 8.4's "Reliability Patterns" — the Deadline Tracker and the Watchdog — against what was actually built, and found the core mechanism of both was already real and already tested (`await_with_deadline` bounds every wait on the opponent and converts expiry to `TECHNICAL_LOSS`; a real daemon thread polls a heartbeat and genuinely hard-exits the process on staleness). Four specific literal claims didn't hold:

1. No outgoing request carried a wire-level timestamp/deadline — the bound was purely a local `asyncio.wait_for` timer, invisible to the receiving peer.
2. There was no Retry path at all before Technical Loss — `mcp_client_prd6.py`'s own docstring said so directly.
3. The Watchdog is a daemon *thread*, not a separate OS process.
4. `persist_state` logged only the state-machine's phase name, not real game state — "so the agent can potentially recover later" overstated what existed.

## Decisions

**(1) Fixed — wire-level `sent_at`/`deadline_at`.** `planner/deadline.py::now_and_deadline(timeout_seconds) -> (sent_at, deadline_at)` computes the pair once (I6: no repeated `time.time() + timeout` arithmetic at each call site). `send_commit`/`send_reveal` (`tools/mcp_client_prd6.py`) and `receive_commit`/`receive_reveal` (`tools/mcp_server_prd6.py`) both carry it now — the Commit-Reveal round trip is the core protocol ch. 8.4 is describing reliability for, and is this PRD's required scope. The receiver logs the peer's declared timing on the matching trace event (`peer_commit_received`/`hint_received` gain `peer_sent_at`/`peer_deadline_at`) and, if the declared deadline has already passed on receipt, logs one extra informational `peer_declared_deadline_already_expired` event. Rule 9 (everything a peer sends is untrusted) means this is purely observational: the receiver's own `await_with_deadline` bound is never shortened, extended, or otherwise touched by what the peer claims. Extending the identical pattern to barrier declaration, capture-claim/response, and Step-0 (`mcp_server_prd9.py`) is a mechanical follow-up sharing the same shape — tracked in `TODO15.md`, not required for this PRD's own milestone (the same "symmetric follow-up, scoped out" precedent PRD 14 already set for the cop's own outgoing hint).

**(2) Deliberately not fixed — no retry.** `_on_reveal_received` applies the peer's hint to the belief map via `belief_map.update_from_hint` — not idempotent. A blind retry on a lost ACK risks the first attempt having actually landed; re-sending would double-apply the same evidence and corrupt the Bayesian belief state. Ch. 8.4's own wording — "triggers **either** a Retry **or** ... Technical Loss" — makes routing straight to `TECHNICAL_LOSS` a fully compliant branch on its own; nothing in the book mandates attempting a retry first. See `README.md` §5's fifth documented-contradiction note for the full "found/chose/why" writeup.

**(3) Deliberately not fixed — thread, not process.** `orchestrator_server.py::_watch_loop` stays a daemon thread. Real multiprocessing would need the heartbeat state shared across a process boundary via IPC — real risk of brushing against rule 1/2's "no shared live state" boundary for comparatively small benefit. Python's GIL already yields during I/O waits, which covers every realistic freeze this codebase can produce (blocking network calls, an unhandled exception, a Python-level infinite loop); only a native/C-level GIL-holding hang would defeat a thread-based watchdog, and nothing in this pure-Python, I/O-bound codebase produces that class of freeze. Kept as a documented, reasoned scope boundary, not silently left as an oversight.

**(4) Fixed — a real structured snapshot.** `orchestrator_server.py::ServerLifecycleMixin._persist_watchdog_state` (wired as `Watchdog`'s `persist_state` callback in `orchestrator.py::__init__`) now logs `own_pos`, `target_pos`, `barriers_placed`, and `steps_taken` alongside the state-machine phase — real, structured `game_state` data, not just a phase string. `Position` has no `__lt__`, so `barriers_placed` is built as `sorted([p.col, p.row] for p in ...)` (list pairs, not bare `Position` objects) to avoid a real `TypeError`. Deliberately **not** a full auto-resume: nothing reads this snapshot back to reconstruct `Board`/`BeliefMap`/`GameState` and rejoin an in-progress match. That would need new state-machine states, a resume negotiation step, and peer-side cooperation — a materially larger feature, out of scope here and left for a future PRD if ever needed.

## A related finding, found during verification — also fixed

While verifying this PRD's changes against the full test suite, a full `tests/unit` run was found to sometimes terminate abruptly partway through with no summary — reproduced identically on the clean, pre-PRD-15 tree via `git stash`, confirming it predates this work entirely. Root cause: `orchestrator_server.py::_watch_loop`'s daemon thread (started by every `run_as_server` call, and by design meant to outlive a single match/process) called the real `os._exit(1)` once ~`watchdog_threshold_seconds` (60s) had elapsed since its orchestrator's last heartbeat. `test_orchestrator_watchdog.py::test_run_as_server_starts_a_watchdog_monitor_that_shuts_down_on_staleness` already documented and neutralized this for its own orchestrator (calling `.heartbeat()` before returning, with an explicit comment on why); no other `run_as_server`-using test fixture across the suite did the same, so once enough real wall-clock time accumulated across a long full-suite run, an early test's abandoned watchdog thread could kill the shared pytest process outright. **This is a test-suite-only hazard, not a production defect**: rule 1/2's one-orchestrator-per-process design means a real deployed peer's watchdog thread simply dies with its own process at normal exit — the failure mode only exists because pytest keeps hundreds of tests' orchestrators alive in one shared, long-running process.

**Fixed, within rule 7's own constraints.** Rule 7 says a *live* match's watchdog must "run" continuously — that requirement is untouched; nothing here lets an active orchestrator silence its own crash protection. What changed: `_watch_loop` now waits on a `threading.Event` (`self._watchdog_stop_event`, `orchestrator.py::_init_cross_thread_signals`) instead of a plain `time.sleep` — `Event.wait(poll_interval_seconds)` doubles as the poll delay and an early-exit signal. `orchestrator_server.py::stop_watchdog_monitor()` sets that event; it's a no-op for an orchestrator whose monitor was never started, and a real deployed peer never needs to call it at all (process exit already takes the thread with it). The fix lives entirely in test infrastructure: `tests/conftest.py`'s new autouse `_stop_watchdog_monitors_after_test` fixture tracks every `Orchestrator` constructed during one test (via a scoped `patch.object` on `__init__`, not a permanent production-code registry) and calls `stop_watchdog_monitor()` on each before the next test starts. Verified end to end: the full `tests/unit` suite, previously dying partway through every time, now completes cleanly (740 passed, 356s) with no abrupt termination.

## Files touched

- `src/cop/planner/deadline.py` — `now_and_deadline`.
- `src/cop/tools/mcp_client_prd6.py` / `src/cop/tools/mcp_server_prd6.py` — commit/reveal timing fields.
- `src/cop/orchestrator_turn.py` / `src/cop/orchestrator_peer_audit.py` — receiver-side logging, `_log_if_peer_deadline_already_expired`.
- `src/cop/orchestrator_commit_reveal.py` — computes and passes `sent_at`/`deadline_at` at both call sites.
- `src/cop/orchestrator.py` / `src/cop/orchestrator_server.py` — `_persist_watchdog_state`, `_watchdog_stop_event`, `stop_watchdog_monitor`.
- `tests/conftest.py` — the autouse watchdog-monitor-teardown fixture.
- `tests/unit/test_prd4_seam.py` — narrowed `_find_target_pos_assignments`'s keyword scan to `GameState(...)` calls specifically, after `_persist_watchdog_state`'s own unrelated `trace.log(target_pos=...)` kwarg tripped the previous, overly broad by-name-only match.
- `README.md` §5 — fifth documented-contradiction note (the no-retry decision).
- Tests: `tests/unit/test_deadline.py`, `tests/unit/test_orchestrator_commit_reveal.py`, `tests/unit/test_orchestrator_watchdog.py`, plus every fake test peer across the suite that registers its own `receive_commit`/`receive_reveal` tool (updated to accept the two new required fields).

## Also verify (acceptance criteria)

```bash
uv run pytest tests/unit/test_deadline.py tests/unit/test_orchestrator_commit_reveal.py tests/unit/test_orchestrator_watchdog.py tests/unit/test_prd4_seam.py -q
uv run ruff check src/cop/planner/ src/cop/tools/ src/cop/orchestrator.py src/cop/orchestrator_server.py src/cop/orchestrator_turn.py src/cop/orchestrator_commit_reveal.py src/cop/orchestrator_peer_audit.py tests/conftest.py
wc -l src/cop/*.py src/cop/planner/*.py src/cop/tools/*.py   # all ≤150
uv run pytest tests/unit -q   # full suite: completes cleanly, no premature os._exit
```

## Explicitly out of scope

- Extending `sent_at`/`deadline_at` to barrier declaration, capture-claim/response, and Step-0 tools (`TODO15.md`).
- Any retry mechanism for peer requests (decision 2 above).
- A separate-process Watchdog (decision 3 above).
- Full match auto-resume from a persisted snapshot (decision 4 above).
