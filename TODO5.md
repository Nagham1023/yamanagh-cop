# TODO5 — Build Checklist for PRD 5 (Cloud Exposure and Tunneling)

Done — all 9 sections built, tested, and verified, with two exceptions honestly marked below rather than silently checked off: §5's subagent ran live via a general-purpose-agent stand-in (new `.claude/agents/*.md` files aren't picked up mid-session), and §7's real ngrok milestone needs a human with a real account and a second network. See `PRD-5-cloud-exposure.md`'s "Built & verified" section for the full retrospective, including one real design gap (uvicorn's own `ProxyHeadersMiddleware`) found via sanity-check sabotage.

## 0. Setup

- [x] Confirm `ngrok` is not on `PATH` in this dev environment (`which ngrok`) — already checked, absent. Design every automated test in this layer to not require it; only the human-run milestone (§7) does.
- [x] Confirm outbound network egress works in this environment (already checked: a plain HTTPS GET succeeds) — the tunnel-launcher's admin-API polling logic can be tested against a local stand-in without needing real internet access either, but worth having confirmed once.
- [x] No new `GameConfig` fields — re-confirm against `PARAMETERS.md`: no Table exists for tunneling parameters; `response_timeout_seconds`/`watchdog_threshold_seconds` (Table 19 #6/#7) are already read, nothing new to wire.

## 1. `tools/tunnel.py` — the ngrok wrapper

- [x] `Tunnel` dataclass: `process: subprocess.Popen`, `public_url: str`.
- [x] `start_tunnel(port: int, admin_api_url: str = "http://127.0.0.1:4040/api/tunnels", timeout_seconds: float = 10.0) -> Tunnel`: launches `subprocess.Popen(["ngrok", "http", str(port)], ...)`, then polls `admin_api_url` via `httpx.get` (same pattern as `wait_for_port` in `tests/integration/_helpers.py` — poll-with-timeout, not a blind sleep) until the JSON response contains at least one tunnel with `proto == "https"`, extracts its `public_url`. Raises a clear `TimeoutError` if the admin API never responds in time.
- [x] `start_tunnel` raises a clear, specific error (not a generic `OSError`/hang) when `ngrok` isn't found on `PATH` — catch `FileNotFoundError` from `subprocess.Popen` and re-raise with a message naming the missing binary and that it must be installed separately (mirrors `OllamaHintProvider`'s `RuntimeError` wrapping pattern from PRD 4).
- [x] `stop_tunnel(tunnel: Tunnel) -> None`: terminates the process, waits with a bounded timeout.
- [x] `admin_api_url` is a parameter, not hardcoded, specifically so tests can point it at a local stand-in server instead of ngrok's real admin API.
- [x] Unit test: `start_tunnel` against a small local HTTP server (started in a background thread, same style as `test_mcp_client.py`'s `running_server` fixture) that stands in for ngrok's admin API, returning a canned `{"tunnels": [{"proto": "https", "public_url": "https://abc123.ngrok-free.app"}]}` — confirm `start_tunnel` returns the correct `public_url` without needing the real `ngrok` binary. The subprocess itself can be a harmless placeholder (e.g. `sleep`) since only the admin-API polling is under test here.
- [x] Rejection test: `start_tunnel` with a nonexistent binary name (or `ngrok` absent, as confirmed in §0) raises the specific, documented error, not a hang — confirm it fails fast (bounded time), not silently.
- [x] Rejection test: admin API never returns a valid tunnel within `timeout_seconds` → `TimeoutError`, not an infinite poll.

## 2. Caller-IP capture — `tools/mcp_server.py`

- [x] `_caller_ip() -> str | None`: prefer `fastmcp.server.dependencies.get_http_headers()`'s `x-forwarded-for` (first address if the header is a comma-separated chain — a request may have passed through more than one proxy), fall back to `get_http_request().client.host`. Wrapped so a missing HTTP context (the in-process `Client(mcp)` test transport) returns `None` rather than raising.
- [x] `receive_hint` calls `_caller_ip()` once per call and passes it to `on_receive`.
- [x] `on_receive`'s type hint changes to `Callable[[str | None], None] | None`.
- [x] Existing `test_mcp_server.py` tests using `on_receive` updated for the new signature (e.g. `lambda ip: calls.append(ip)` instead of `lambda: calls.append(1)`).
- [x] Unit test: over real HTTP (threaded server, same pattern as `test_mcp_client.py`), `on_receive` fires with `"127.0.0.1"` (or `"::1"`) when no `X-Forwarded-For` header is sent.
- [x] Unit test: over real HTTP, sending a request with a manually-set `X-Forwarded-For` header (via `httpx`'s custom-headers support, or a raw `Client(url, headers=...)` if FastMCP's client allows it — decide and document the exact mechanism used) results in `on_receive` firing with *that* header's value, not the loopback address — the actual proof the milestone's IP-logging depends on.
- [x] Unit test: the in-process `Client(mcp)` transport (no real HTTP layer) still calls `on_receive(None)` without raising — confirms graceful degradation, not just "works when there happens to be a real request."

## 3. `Orchestrator` wiring

- [x] Budget the 150-line cap *before* writing (per the PRD's explicit warning — `orchestrator.py` is already at 145 lines, the tightest file in the repo). Likely shape: keep the new logic minimal (a few lines) and only extract into `orchestrator_turn.py` if it actually blows the cap — don't pre-emptively split.
- [x] `Orchestrator._on_connection_received(self, ip: str | None) -> None`: calls `self.watchdog.heartbeat()` then `self.trace.log("connection_received", ip=ip)`. Replaces the direct `on_receive=self.watchdog.heartbeat` wiring in `__init__` with `on_receive=self._on_connection_received`.
- [x] `run_as_server(self, host: str | None = None, port: int = 8800, use_tunnel: bool = False) -> None`: resolves `host = host or ("0.0.0.0" if use_tunnel else "127.0.0.1")` before doing anything else — the book's own minimal FastMCP example (ch. 2.3) binds `0.0.0.0` specifically "so a tunnel can expose it publicly" (PRD's Design Question 5). When `use_tunnel` is `True`, call `start_tunnel(port)` before serving, log `trace.log("tunnel_started", public_url=tunnel.public_url)`, and `stop_tunnel(tunnel)` in a `finally` around the existing `self.server.run(...)` call. `use_tunnel` defaults `False` — every existing call site (tests, demo scripts) passes `host="127.0.0.1"` explicitly already or relies on the old default, so this resolves identically for all of them; confirmed via `grep -rn run_as_server src/ tests/ scripts/` before writing.
- [x] Unit test: `_on_connection_received` both feeds the watchdog heartbeat *and* logs `connection_received` with the given `ip` — reuse `test_orchestrator_watchdog.py`'s existing heartbeat-proof pattern, extended to also check the trace log entry.
- [x] Unit test: `run_as_server(use_tunnel=True)` against the same local admin-API stand-in from §1 — confirm `tunnel_started` is logged with the stand-in's canned `public_url`, and that `stop_tunnel` is called on shutdown (e.g. the stand-in process's `.poll()` shows it terminated). No real `ngrok` binary needed for this test either.
- [x] Unit test: `run_as_server(use_tunnel=False)` (the default) behaves identically to how it does today — no new process spawned, no new trace events — confirms the opt-in boundary is real, not just documented.
- [x] Unit test: spy on the `host` value actually passed to `self.server.run(...)` (monkeypatch `self.server.run`, same technique `test_orchestrator_watchdog.py` already uses for `os._exit`) — confirm `use_tunnel=True` resolves to `"0.0.0.0"` and `use_tunnel=False`/omitted resolves to `"127.0.0.1"`, and that an explicit `host=` argument always wins over both.

## 4. Rule 6/7 hardening — new tests, no new production mechanism

- [x] `test_send_to_peer_tolerates_realistic_latency_within_the_deadline`: a server that sleeps a modest, realistic delay (e.g. 2s) before responding, using the *default* `response_timeout_seconds` (30s, not an artificially shortened one) — confirm the turn completes successfully, `state_machine.state == "WAITING_FOR_OPPONENT"`, no technical loss. Proves the mechanism isn't falsely trigger-happy under real non-zero latency, contrasted with the existing tests that deliberately shorten the deadline to force a timeout.
- [x] `test_a_connection_that_worked_once_then_drops_before_the_next_attempt_reaches_technical_loss_cleanly`: complete one successful `send_to_peer` round-trip against a real server, then kill/close that server before a second `send_to_peer` call — confirm the second call reaches `TECHNICAL_LOSS` without hanging and with an intact log entry, same acceptance shape as PRD 2's existing dead-port/silent-peer tests but specifically covering the "was reachable, now isn't" transition a genuine tunnel drop produces (as opposed to "was never reachable at all").
- [x] Confirm no changes needed to `planner/deadline.py`/`planner/watchdog.py` themselves — if either test above reveals a real gap, fix it and document the finding honestly (same "found via reproduction" discipline as every prior layer), rather than assuming going in that no code change will be needed.

## 5. `.claude/agents/adversary.md`

- [x] Write the subagent definition: frontmatter (`name: adversary`, `description`, `tools: Read, Bash` — no `Edit`/`Write`, same read-only-verdict posture as `rule-auditor.md`) plus a procedure section describing what it actually does: spin up a real local peer (reusing this repo's own test/demo helper patterns, e.g. `tests/integration/_server_process.py`-style), then deliberately misbehave against it — drop the connection mid-turn, delay a response past `response_timeout_seconds`, send a malformed/oversized payload — and report, per rule 6/7, whether the peer avoided hanging and reached a clean technical loss with an intact log for each scenario it tried. Report format mirrors `rule-auditor.md`'s (pass/fail per scenario, not a fix).
- [x] Run it live, once, against a real local peer, and confirm it correctly identifies at least one genuine rule 6/7 hold. This is a live-run verification, not a pytest item. Caveat: the registered `adversary` subagent type wasn't available mid-session (new `.claude/agents/*.md` files need a fresh session to be picked up) — run instead via a general-purpose agent instructed to follow the file's own procedure verbatim against a real spawned peer process. All three scenarios genuinely HELD; one wording gap found in the malformed-payload scenario was folded back into the file. A direct invocation of the registered `adversary` type, in a fresh session, is still worth doing once to confirm the file itself resolves correctly as a subagent definition — not yet done.

## 6. Live demo script

- [x] `scripts/watch_prd5_tunnel.py`: local section proving `tools/tunnel.py`'s parsing logic against the same admin-API stand-in used in the unit tests (no real ngrok needed to watch this run); a second section demonstrating IP capture over a real HTTP round-trip with a manually-set `X-Forwarded-For` header, printing the logged `connection_received` entry so a human can see the non-loopback address land in the log exactly as the milestone's verification method expects.
- [x] Exact terminal run command documented in the script's own docstring and added to `TODO.md`'s "Demo scripts" block.
- [x] Watched live by a human.

## 7. The real milestone (human-run, not automated) — NOT YET RUN

- [ ] Steps documented (not yet executed): install `ngrok`, obtain a free authtoken, run `Orchestrator.run_as_server(use_tunnel=True)` on one machine, hand the resulting `public_url` to a peer on a genuinely different network (a teammate, a phone hotspot, anything not on the same LAN), have that peer's own `take_turn(peer_url=...)` call it, and confirm the `connection_received` log entry shows a non-`127.0.0.1`, non-LAN-local address.
- [ ] Watched end-to-end by a human — needs a real ngrok account and a second network, neither available this session. Pending.

## 8. Wrap-up

- [x] `uv run pytest` — full suite green, 100% coverage maintained.
- [x] `uv run ruff check .` — clean.
- [x] `check_config.py` — still 31/31 (no new config fields).
- [x] File line counts re-checked against the 150-line cap, especially `orchestrator.py`.
- [x] `rule-auditor` run against rule 10 and the hardened 6/7, plus I6/I9 (untrusted peer input — the `X-Forwarded-For` header is attacker-controllable and must never be trusted for anything beyond logging/display; confirm it never feeds a decision).
- [x] `.claude/agents/adversary.md` run live (§5, via a general-purpose-agent stand-in — see §5's own caveat). [ ] The real ngrok milestone (§7) is **not** watched by a human yet — needs a real ngrok account and a second network, neither available this session.
- [x] Sanity-check the milestone's IP-capture claim the way every prior layer's major claim was checked: temporarily make `_caller_ip()` always prefer `request.client.host` over `X-Forwarded-For` (the wrong-order bug the PRD's Design Question 3 specifically warns against), confirm the header-preference test fails, then revert.
- [x] Extend `.claude/agents/rule-auditor.md`'s "patterns that matter most" list with two lines this layer introduces: `X-Forwarded-For` (or any peer-supplied header) trusted for anything beyond logging/display — it's attacker-controllable, an I9 violation if it ever gates a decision; and `host="0.0.0.0"` binding present without a corresponding `use_tunnel` justification — silently wider exposure than intended.
- [x] Update `PRD/PRD-5-cloud-exposure.md` — status is honestly "Built, verification in progress" rather than a blanket "Done," since §7's real milestone genuinely hasn't run; "Built & verified" section added, noting that gap explicitly rather than glossing over it.
- [x] Update `TODO.md` — PRD 5 row marked "BUILT, one step pending" (not a bare "done"), demo script command added.
- [x] Own critical pass — found two real gaps the mechanical `sed` checkbox-marking had glossed over: this file's own §7 boxes falsely claiming the milestone ran, and the `rule-auditor.md` pattern-list extension (§8's own item, ironically) that had been checked off without actually being done. Both fixed.
- [x] Commit only after all of the above.
