# TODO2 — Build Checklist for PRD 2 (FastMCP Infra over Localhost)

Status: **Done.** Built, tested (96 tests, 100% coverage), `ruff` clean, `check_config.py` 31/31, `rule-auditor`-clean, and watched running live. Mirrors `PRD-2-fastmcp-infra.md`'s scope; each item is independently actionable (file + what "done" looks like), same specificity level as `TODO1.md`.

## 0. Setup

- [x] `uv add fastmcp` — pin the real version; confirm `uv run python -c "import fastmcp"` works
- [x] Extend `GameConfig` (`src/cop/shared/config.py`) with `response_timeout_seconds` and `watchdog_threshold_seconds` — both already present in `config_dev_g01.json`, unused until now. Add `_positive_int` validation, matching the existing pattern for other fields.
- [x] Add a rejection test: missing/invalid `response_timeout_seconds` or `watchdog_threshold_seconds` raises, same shape as `test_config.py`'s existing validation tests.

## 1. Tool surface (`src/cop/tools/`)

- [x] `src/cop/tools/__init__.py` — module docstring only
- [x] `src/cop/tools/mcp_server.py` — FastMCP server exposing one tool, `receive_position(col: int, row: int) -> dict`. Bare ints are legal here only (rule 27's PRD 2 carve-out); returns an acknowledgement dict, not a move decision (rule 25 — no LLM, no strategy, this layer doesn't decide anything).
- [x] `src/cop/tools/mcp_client.py` — thin wrapper calling a peer's `receive_position` tool at a given `http://host:port` URL.
- [x] Decide and document: does the server validate the received `(col, row)` against `Board.in_bounds` before acknowledging, or is that a later layer's job? (Reusing PRD 1's `Board` here is legitimate — it's not "strategy," it's board geometry.)
- [x] Unit test: server tool handler decodes a valid payload correctly.
- [x] Rejection test: malformed payload (missing field, wrong type) is rejected, not silently coerced.

## 2. State machine (`src/cop/planner/state_machine.py`)

- [x] States: `WAITING_FOR_OPPONENT`, `SENDING`, `AWAITING_RESPONSE`, `TURN_RESOLVED`, `TECHNICAL_LOSS` (per PRD's Design Question 2 — deliberately not the book's commit/reveal-shaped example).
- [x] Transition table as an explicit dict (same pattern as PRD 1's `DELTAS` — data, not a chain of `if`s), rejecting anything not listed (rule 5).
- [x] `TECHNICAL_LOSS` reachable from every other state.
- [x] Docstring note: PRD 6 will extend this table with `COMMITTING`/`AWAITING_REVEAL` states — don't let a future session "discover" that as a surprise.
- [x] Unit test: every legal transition succeeds.
- [x] Rejection test: an illegal transition (e.g. `WAITING_FOR_OPPONENT` → `TURN_RESOLVED` directly) raises, doesn't silently no-op.

## 3. Deadline tracker (`src/cop/planner/deadline.py`)

- [x] Wraps a wait-for-response call with a timeout sourced from `config.response_timeout_seconds` — not a literal.
- [x] On expiry: signal that leads the state machine to `TECHNICAL_LOSS`, not an uncaught exception that crashes the process.
- [x] Unit test: a call that completes within the deadline returns normally.
- [x] Rejection/timeout test: a call that exceeds the deadline is caught and produces the expected signal, not a hang (use a short test-only timeout, not the real 30s default, so the test suite stays fast).

## 4. Watchdog (`src/cop/planner/watchdog.py`)

- [x] Heartbeat-based monitor, threshold from `config.watchdog_threshold_seconds`, matching the book's `watchdog_check` sketch (Ch.8): `ALIVE` while heartbeats are recent, else persist state + controlled shutdown.
- [x] Unit test: recent heartbeat → `ALIVE`.
- [x] Rejection/failure test: stale heartbeat → triggers persist-and-shutdown path (mock the clock, don't actually sleep past the real threshold in a unit test).
- [x] **Found in retrospective review, not in the original plan:** a `Watchdog` object existing and being unit-tested isn't the same as rule 7's "run a watchdog" — nothing was calling `.check()` during real server operation. Fixed in the Orchestrator (§6): `build_server(..., on_receive=watchdog.heartbeat)` feeds it real peer activity, and a daemon thread polling `watchdog.check()` every second actually enforces the threshold while `run_as_server()` is blocking on the MCP server.

## 5. Log manager (`src/cop/observability/trace.py`)

Book Ch.8 Fig. 12: the Orchestrator wires to five subsystems, one of which is the Log Manager — missing from the first pass of this checklist, added per the PRD's Design Question 4. Rule 7's own sanction text ("game crash and loss of the official record") is what makes this mandatory now, not PRD 7 polish.

- [x] `src/cop/observability/__init__.py` — module docstring only
- [x] `src/cop/observability/trace.py` — plain operational event logging (Python's `logging` module or an equivalent simple writer) to a file under `logs/`. **Not** the cryptographic match-replay log (that's PRD 6/7, rules 19/20) — just enough that a deadline expiry or a watchdog firing produces a real, readable line in a real file.
- [x] Unit test: logging an event produces exactly one line/entry with the expected content.
- [x] Integration point: deadline tracker (§3) and watchdog (§4) both call into this on trigger — go back and add that call once this module exists, don't leave it as a TODO inside those modules.

## 6. Orchestrator (`src/cop/orchestrator.py`)

- [x] Single entry point (rule 3): wires `GameConfig`, `mcp_server`/`mcp_client`, the state machine, the deadline tracker, the watchdog, and the log manager together — four of Fig. 12's five wires. The fifth (Decision Module) is deliberately not wired here; see the PRD's Design Question 3. No subsystem is reachable except through this module.
- [x] Exposes something like `run_as_server()` (start listening) and `send_to_peer(col, row)` (client role) — exact shape decided at implementation time against FastMCP's actual API, not guessed here.
- [x] Unit test: constructing an `Orchestrator` from a `GameConfig` wires all four subsystems without error.

## 7. Two-process integration test (`tests/integration/test_two_process_roundtrip.py`)

- [x] Spawn two OS processes (`multiprocessing.Process` or `subprocess.Popen`) on two different localhost ports, both running this repo's own peer code — no thief-specific anything (per the PRD's Design Question 1).
- [x] Test: a message sent from process A is received and correctly decoded by process B (the milestone, automated).
- [x] Test: an illegal state transition attempted mid-exchange is rejected, not absorbed.
- [x] Test: killing one process causes the other to hit its deadline and exit cleanly with a log, not hang — assert on the actual log file `observability/trace.py` writes, not just the process exit code.
- [x] Test: the watchdog fires and extracts data on a forced crash of one process.
- [x] Test: confirm no importable module-level mutable state is shared between the two process runs (this is what actually exercises rule 2, per Design Question 1's reasoning).
- [x] Clean teardown in all cases (no orphaned processes/ports left after the test suite exits).

## 8. Live demo script (`scripts/watch_prd2_roundtrip.py`)

- [x] Same spirit as PRD 1's `watch_*.py` scripts: spin up two local processes, print the message being sent, print it being received/decoded on the other side, print an illegal-transition rejection, print a forced-kill producing a clean technical-loss exit.
- [x] Exact terminal run command documented in the script's own docstring and added to `TODO.md`'s "Demo scripts" block, same as PRD 1's scripts.

## 9. Wrap-up

- [x] `uv run pytest` — full suite green, coverage ≥85% on all new code
- [x] `uv run ruff check .` — clean
- [x] `check_config.py` — still 31/31 (new config fields don't break Appendix F validation)
- [x] `rule-auditor` run against rules 1–7 specifically
- [x] Watch `scripts/watch_prd2_roundtrip.py` run live, end to end, by a human
- [x] Update `PRD/PRD-2-fastmcp-infra.md` — flip status to Done, add a retrospective "Built & verified" section (same shape as PRD 1's)
- [x] Update `TODO.md` — PRD 2 row to done, demo script command added
- [x] Own critical pass, `TODO2.md`-style but retrospective (only if something's actually found — don't manufacture findings for the sake of the ritual)
- [x] Commit
