# PRD 2 — FastMCP Infrastructure over Localhost

Status: **Done.** Built via `TODO2.md`, verified by `tests/unit/`, `tests/integration/`, a clean `rule-auditor` pass (rules 1–7, I6, I9, I10 all CLEAN, no fatal/non-fatal violations), and a live run of `scripts/watch_prd2_roundtrip.py`. 98 tests + 1 deliberate `xfail`, 100% coverage, `ruff check .` clean, `check_config.py` 31/31.

## Built & verified

The milestone (a geometric message leaving agent A over localhost, received and correctly decoded by agent B) is proven three ways: the automated `test_message_from_process_a_is_received_and_decoded_by_process_b` (real `subprocess.Popen` processes, not threads), the four-part live demo script, and `rule-auditor`'s independent read of the same code.

One gap surfaced during my own retrospective pass (mirroring `TODO1.md`'s discipline) that `rule-auditor` didn't flag, because it checked the *wiring* of `persist_state`/`controlled_shutdown` to the trace log but not whether anything actually drove `watchdog.check()` during real server operation: `Orchestrator.run_as_server()` constructed a `Watchdog` but never called `.check()` or fed it a `.heartbeat()` — rule 7 says "**run** a watchdog," and a tested-but-dormant class doesn't satisfy that. Fixed by:

- `tools/mcp_server.py`'s `build_server()` gained an optional `on_receive` callback, invoked on every successful `receive_position` call
- `Orchestrator.__init__` now constructs `self.watchdog` before `self.server`, and wires `build_server(config, on_receive=self.watchdog.heartbeat)` — every message from the peer is a real heartbeat, not just wall-clock-since-start
- `run_as_server()` starts a daemon thread (`_start_watchdog_monitor`) that polls `watchdog.check()` every second; on `"SHUTDOWN"` (which has already run `persist_state`/`controlled_shutdown`), it force-exits the process with `os._exit(1)` — the frozen process actually ends, not just logs that it should have

Covered by `test_receiving_a_position_feeds_the_orchestrators_watchdog_heartbeat`, `test_run_as_server_starts_a_watchdog_monitor_that_shuts_down_on_staleness`, `test_watchdog_monitor_stays_alive_while_heartbeats_keep_arriving`, and `test_on_receive_hook_fires_on_every_successful_call`.

## Three additional scenario tests (requested, added after the layer was otherwise closed)

- **Overlapping exchange** (`tests/integration/test_concurrent_exchange.py`): two real OS processes each send AND receive within the same wall-clock window, not a one-way round-trip — `_server_process.py` gained an optional `--peer-port` so a spawned process can act as client and server in the same run. Proves no cross-talk between the two independent processes even under concurrent inbound/outbound activity (rule 2).
- **Silent peer** (`tests/unit/test_orchestrator_peer_failures.py::test_send_to_peer_against_a_silent_peer_hits_the_deadline_not_a_socket_error`): a raw socket that accepts the TCP connection and then never responds, closes, or resets — no socket-level error ever arrives, so only the deadline tracker can end it. Distinct from the existing dead-port test (immediate connection-refused) and slow-peer test (a late-but-real response).
- **Rule 27 removal guard** (`tests/unit/test_mcp_server.py::test_the_numeric_position_tool_is_gone_once_prd4_lands`): a `pytest.mark.xfail(strict=True)` asserting `receive_position` is absent from the tool surface. It fails as expected today (the tool is still there, correctly, per PRD 2's carve-out); the moment PRD 4 removes the tool, this flips to an unexpected pass, and `strict=True` turns that XPASS into a hard suite failure — so the marker can't be forgotten. Both the tool and the test carry the literal grep string `RULE-27-REMOVE-AT-PRD-4` (documented in `CLAUDE.md`'s "Known trap" section) so `rule-auditor` or a human can find both ends with one grep.

`tests/integration/_helpers.py` was extracted to hold the shared spawn/wait logic now used by both integration test files and `_server_process.py` itself, avoiding a third copy. `test_orchestrator.py` was split three ways (construction/happy-path, peer-failure modes, watchdog wiring) to stay under the 150-line house cap after these additions.

## Build

Split into two processes. Stand up each peer's FastMCP server, define the tool surface, connect this peer's client to the other's server. Introduce the Orchestrator, the state machine, the deadline tracker, the watchdog, and a minimal operational log manager (see Design Question 3) — the book's own Orchestrator diagram (Ch.8, Fig. 12) wires the Orchestrator to five subsystems; PRD 2 builds four of them (MCP Connector, Log Manager, Deadline Tracker, Watchdog) and leaves the fifth (Decision Module) to PRD 3, see Design Question 3.

Messages at this stage carry bare coordinates — the one and only point in the project where that's legal, because the language layer (PRD 4) doesn't exist yet. Rule 27 makes removing this mandatory before any counted game.

## Explicitly out of scope

- A strategy module, heuristics, or Q-learning (PRD 3) — this layer moves nothing on its own
- Natural language, scent, hints, or an LLM call of any kind (PRD 4)
- Tunneling/public exposure (PRD 5) — localhost only
- Commit-Reveal, nonces, hashing, or Step-0 (PRD 6) — see Design Question 2
- GUI, Replay app, Gmail, the Gatekeeper (PRD 7)
- Any dependency on the thief repo existing or being reachable — see Design Question 1

## Rules owned

| Rule | What it requires |
|---|---|
| 1 | Cop and thief run in two completely separate OS processes |
| 2 | No shared memory/variables between the two sides, ever |
| 3 | `Orchestrator` is the single entry point to every subsystem |
| 4 | A proper state machine manages game states |
| 5 | Illegal state transitions are rejected, not absorbed |
| 6 | A deadline tracker prevents freezing while waiting on the opponent |
| 7 | A watchdog monitors the process and extracts data on crash — the rule's own sanction text is "game crash **and loss of the official record**," so this rule is what makes the Log Manager mandatory now, not optional polish |

## Milestone

A geometric message leaving agent A over localhost is received and correctly decoded by agent B.

## Design questions answered here (not left for code-time guessing)

**1. How is this tested without a thief peer?** This repo only ever contains the cop role (rules 1/2) — the thief repo is a teammate's independent work, not something this layer's own verification depends on. The milestone as written says *agent A* and *agent B*, not cop and thief, because the transport/orchestrator/state-machine/deadline/watchdog code being built here is generic peer infrastructure, not brain logic — identical in shape to whatever the thief repo independently builds for itself. PRD 2 is verified by spawning **two separate OS processes running this repo's own peer code**, on different ports, and proving they round-trip a message correctly. This is also the right way to prove rule 2: running two instances of the *same* module in separate interpreters is what would actually surface an accidental shared-global bug — a different thief implementation wouldn't test that any better. Real cross-repo integration against the actual thief is a later, separate concern (PRD 5+), not this layer's job.

**2. How big should the state machine be at this layer?** The book's own worked example (Ch.8, Fig. 11) shows `WAITING_FOR_OPPONENT → COMPUTING_MOVE → COMMITTING → AWAITING_REVEAL → VERIFYING → TECHNICAL_LOSS` — but that bakes in Commit-Reveal, which is PRD 6's rules (17–19), not PRD 2's (1–7). Building `COMMITTING`/`AWAITING_REVEAL` states now, with no real commit-reveal behind them, would be a half-finished stub. This layer's state machine is scoped to what actually exists — a round-trip message exchange, nothing more: `WAITING_FOR_OPPONENT → SENDING → AWAITING_RESPONSE → TURN_RESOLVED`, with `TECHNICAL_LOSS` reachable from any state (deadline expiry or watchdog-detected crash). PRD 6 extends this same transition table with commit/reveal states once Commit-Reveal is actually built — noted in the state-machine module's own docstring so it isn't a surprise later.

**3. Why does the Orchestrator only wire four of Fig. 12's five subsystems, and why doesn't the tool signature match Ch.2's own code sample?** Two deliberate, documented gaps against the book, not oversights:

- *Decision Module deferred.* Fig. 12's fifth wire is the move-decision/strategy brain — that's PRD 3's rule (25) and the `BrainBase` contract, not PRD 2's. Leaving it unwired here is the same kind of correct scoping PRD 1 used for barrier "forgo move" (deferred until turn state existed, and `rule-auditor` confirmed that was a correct deferral, not a violation). `orchestrator.py` gets extended to wire a Decision Module in PRD 3, not built with a fake placeholder now.
- *Bare coordinates, not `signed_move`/`signature`.* Ch.2 §2.3.2's illustrative server code already shows a crypto-shaped tool (`receive_move(signed_move: str, signature: str)`), because that section is teaching FastMCP syntax against the *eventual* tool shape. `PLAN.md`'s own staging (and CLAUDE.md's "Known trap") is explicit that PRD 2 carries bare coordinates, with signing arriving in PRD 6 — book-body illustrations aren't binding over the project's staged layering (spec-guard's own precedence rule). `receive_position(col: int, row: int)` is the correct shape for this layer specifically.

**4. What does the Log Manager actually log, and how is that different from PRD 6/7's match log?** Plain operational events only — a deadline expiring, the watchdog firing, a technical loss occurring — written with Python's `logging` module (or an equivalent simple writer) to a file under `logs/`. This is **not** the cryptographically-hashed, Commit-Reveal-backed match-replay log that PRD 6 (rule 19, audit) and PRD 7 (rule 20, the Replay app) build — that's a different and much heavier artifact, still entirely out of scope here. This module exists solely so rule 7's "intact log" requirement and the milestone's "exit cleanly with a log" criterion are real, checkable things in PRD 2.

## Also verify (acceptance criteria, checked once built)

- An illegal state transition is rejected rather than absorbed
- Killing one peer causes the other to hit its deadline and exit cleanly with a log, rather than hanging — the log is a real file written by `observability/trace.py`, not just a print statement
- The watchdog fires and extracts data on a forced crash
- The two processes share no importable live state (proven by the two-same-module-in-separate-processes test design above)
- `response_timeout_seconds` and `watchdog_threshold_seconds` are read from config, not hardcoded (I6) — both fields already exist in `config_dev_g01.json`, unused until this layer

## New dependency

`fastmcp` — not yet in `pyproject.toml`. Exact version pinned by `uv add fastmcp` at implementation time, not guessed here.

## Builds on

PRD 1's `domain/` and `shared/config.py` are reused as-is (board/movement/barriers/capture/scoring don't change); this layer adds `tools/`, `planner/`, `observability/` (seeded minimally here, extended by PRD 7), and `orchestrator.py` around them, per PLAN.md §4's component tree.
