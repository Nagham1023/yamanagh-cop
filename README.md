# yamanagh-cop

The **cop** peer of a two-peer, judge-free pursuit game — a final project for
*Orchestration of AI Agents*, Dept. of Computer Science, University of Haifa
(spec: book v3.0.0, Dr. Yoram Reuven Segal). This repo contains exactly one
role, cop, never both (rules 1/2); the thief role lives in a separate repo
and runs as a separate OS process. See `CLAUDE.md` for the repo's own
non-negotiable invariants, `PLAN.md` for the full architecture, and `PRD/`
+ `TODO*.md` for the per-layer design/build history.

## Companion (thief) repo

[yamandahle/thief-peer](https://github.com/yamandahle/thief-peer) — the thief role for this
match (rule 49's four cross-links). `config/game.toml`'s `[repos]` block holds the same
negotiated URLs used by the report bundle (`tools/report_bundle.py`); this line is the
human-readable pointer the README itself is required to carry.

## Running it

```bash
uv sync

# run this peer — role is fixed by which repo you are in, not a flag
uv run python -m cop peer

# replay and verify a recorded match
uv run python -m cop replay --log logs/log_<game_id>_g<NN>.json

# tests
uv run pytest --cov=cop --cov-report=term-missing

# validate a config against the mandatory parameter table
uv run python .claude/skills/spec-guard/scripts/check_config.py config/shared/config_<game_id>_g<NN>.json
```

---

## 1. The Dec-POMDP model

Neither agent observes the true world state. The system is modelled as a
**Decentralized Partially-Observable Markov Decision Process** with `n = 2`
(book §1.3) — cop and thief, fixed by the formalism itself. There is no
third agent and no supervisor: a supervisor would be the referee the whole
project exists to eliminate (`PLAN.md` §2).

Each agent builds a private belief over the opponent's position from two
channels only:

- a **decaying scent field** (`memory/scent.py`) — physically grounded,
  emitted wherever the agent has actually stood, decaying every subsequent
  turn (ch. 4.3's own formula); this channel cannot be faked, since an agent
  can only strengthen scent where it truly is;
- a short **natural-language hint** (`reasoning/hint.py`) — the sender is
  permitted to falsify it (rule 26/27: free text, never coordinates).

`memory/belief.py::BeliefMap` fuses both into a genuine Bayesian posterior
— `P(state|evidence) ∝ P(evidence|state)·P(state)`, always renormalized to
1 — with a reliability coefficient (`_HINT_RELIABILITY`, ch. 6.4's
"מקדם אמינות") down-weighting the text channel relative to the
uncorruptible scent channel. That asymmetry — one channel truthful by
construction, the other freely corruptible — is the sharpest design fact in
the project, and is why a Bayesian belief map beats a credulous one.

Integrity, since there is no referee, is established mathematically: a
SHA-256 **Commit-Reveal** protocol (`integrity/commit_reveal.py`,
`integrity/nonce.py`) plus a full **mutual log audit** at game end
(`integrity/audit.py` for the self-consistency half, `integrity/peer_trace.py`
for the genuinely bilateral half — see §2 below).

## 2. FastMCP orchestration dilemmas

The two peers talk over **MCP** (via FastMCP, `tools/mcp_server*.py` /
`tools/mcp_client*.py`), where each side is simultaneously server and
client. Three failure modes the book names for multi-agent systems lacking
a real orchestration layer, and how this repo answers each one
(`PLAN.md` §2):

| Failure mode | Form here | Mechanism |
|---|---|---|
| **Contradictory outputs** | The two teams disagree on who won | Commit-Reveal plus the end-of-game mutual audit *is* the deciding mechanism; an unresolved contradiction voids the game for both sides, not a dispute to arbitrate (rules 19, 35, 36) |
| **Convergence failure / infinite loops** | Both peers blocked waiting on each other | Deadline tracker (`planner/deadline.py`) on every wait; a watchdog (`planner/watchdog.py`) supervising the process; an explicit state machine (`planner/state_machine.py`) that rejects illegal transitions instead of absorbing them (rules 4–7) |
| **Task duplication** | Repeated LLM calls, recomputed inference | Token budget declared and reported (`observability/cost.py`, rule 54); `template`/`ollama` as zero-token defaults |

**Turn management.** `planner/state_machine.py::PeerStateMachine` implements
the book's own Commit-Reveal cycle verbatim (ch. 8, Fig. 11):
`WAITING_FOR_OPPONENT → COMPUTING_MOVE → COMMITTING → AWAITING_REVEAL →
VERIFYING → WAITING_FOR_OPPONENT`, cyclic, with `TECHNICAL_LOSS` as the one
terminal state reachable from the states that represent an active wait on
the peer.

**Network-failure handling.** Every wait on the opponent
(`await_with_deadline`, `planner/deadline.py`) is bounded; a timeout or a
malformed response drives the state machine to `TECHNICAL_LOSS` rather than
hanging — proven by the `adversary` test harness (drops the connection
mid-turn, delays past deadline, sends malformed payloads) and by dedicated
tests such as `test_take_turn_against_an_unreachable_peer_reaches_technical_loss_before_computing_a_move`.

**Orchestrator/Gatekeeper roles.** `orchestrator.py` is the single entry
point into every subsystem (rule 3) — domain logic, memory, reasoning,
integrity, and tools are never reached directly by a caller. It doubles as
this project's SDK facade (`software_submission_guidelines-V3.pdf` §4.1/
§17.2's requirement — no separate `sdk.py` needed). `policy/gatekeeper.py::
ApiGatekeeper` is the guide's own facade shape (`execute()`, `get_queue_status()`)
composing three accumulating protections in the book's own order (ch. 9.3.1,
Fig. 13): Quota Manager → Token Bucket → DOS Detector, fail-fast on a gate
rejection, retrying only on the wrapped call's own transient failures
(Table 19's `retry_backoff_sec`/`max_retries`, read from config, never
hardcoded).

## 3. The decision-making mechanism actually implemented

**Python decides the move, always (rule 25).** The language model — when
one is configured at all; the zero-token `template` provider is the default
— touches only the verbal hint (`tools/hint_providers.py`). The objective
function a hint could try to hijack is never reachable from text.

`reasoning/cop_brain.py::CopBrain` is the shipped heuristic: greedy
Manhattan-distance descent toward the current belief target, among legal
orthogonal moves (bounds-checked via `domain/movement.py`, barrier-checked
via `domain/barriers.py`), `STAY` only when every orthogonal move is
illegal. The observe → decide → act → verify loop maps one-to-one onto the
source tree: **observe** (`memory/` — scent + hint fused into belief),
**decide** (`reasoning/` — pure Python, no LLM in the decision), **act**
(`tools/` — commit, then reveal, over MCP), **verify** (`integrity/` — the
self-audit and, as of this layer, the bilateral peer-audit).

**The bilateral mutual audit (rule 36, closing PRD 6's own acknowledged
gap).** `integrity/audit.py::run_mutual_audit` is the *self*-consistency
half: this side's own log, replayed against this side's own later-revealed
nonces. `integrity/peer_trace.py::run_peer_audit` is the genuinely bilateral
half ch. 5.4 actually requires: it reconstructs the **peer's** own
committed-and-revealed `State`/`Move`/`Intent`/`Nonce` (state is never sent
over the wire at all — it's replayed from the peer's own publicly known
start position through their own revealed moves) and compares the
recomputed `Hcommit` against what the peer actually broadcast. The
adversarial test proving this is genuinely bilateral, not a renamed
self-check, is `test_a_tampered_peer_move_fails_the_bilateral_audit`
(`tests/unit/test_peer_trace.py`).

## 4. RL learning curves

**Not built.** The course did not teach reinforcement learning, and the
book states plainly that a fully competitive agent can be built from
heuristics alone (`PLAN.md` §7, Optional Layer 8). `CopBrain`'s heuristic
(§3 above) is deterministic, not learned — there is no training run and no
learning curve to report here. Treated honestly as out of scope rather than
implied and left unimplemented.

## 5. Live GUI and Replay App (Verified OK)

**Live GUI** (`observability/live_gui_render.py::render_state`) renders
local truth only (rules 8/9, ch. 7.2's own three-item definition — own
position, scent sensed, hints received, no bird's-eye view): exactly six
inputs reach the render call — this side's own `Position`,
`BeliefMap._probabilities`, the current `PeerStateMachine` state string for
the turn banner, this side's own placed `BarrierSet.placed`, this side's
own currently-sensed `ScentField.full_field()`, and the most recent hint
text this side actually received from the opponent (all local-truth-safe,
same category as `own_pos` — nothing here is an opponent secret). It never
receives `GameState.target_pos` or the true opponent position — this
repo's own `Orchestrator` never even holds that value (rule 1/2). Enforced
by introspecting `render_state`'s own parameter list
(`test_render_state_signature_admits_no_true_opponent_position_or_board`),
not by inspecting a screenshot. The window shows two side-by-side heatmap
panels — belief (red) and currently-sensed scent (blue), a deliberately
different hue so the two signals never read as one — plus the turn banner
and a hint-text label below it. The belief panel marks the cop's own cell
with a blue circle and a 'C' label, stars the currently most-likely
believed opponent cell, and paints placed barriers as solid dark squares
that visually win over whatever heatmap color would otherwise show there.
Demoed live end-to-end by `scripts/watch_prd7_live_gui.py`.

**Replay App** (`observability/replay_viewer.py::ReplayViewer`) reads a
recorded `log_<game_id>_g<NN>.json`, steps through it, and stamps
`Verified OK` / `TAMPERED` by wrapping the real
`integrity/audit.py::run_mutual_audit` — never a simplified sketch of the
audit logic. Demoed live, both the honest path (`Verified OK`) and the
adversarial path (a tampered log correctly flagged `TAMPERED`), by
`scripts/watch_prd7_replay.py`. Navigation genuinely halts at the first
tampered step — `Forward` disables and the step label reads "further steps
blocked (disqualified)" — rather than letting you page straight past the
point of disqualification.

**A documented design contradiction, and how it was resolved.** This
module's own docstring argues for a single bulk cryptographic audit — one
pass/fail verdict computed once over the whole log on load. A separate
product-style spec instead describes a per-step `verify_step`-shaped UI
that recalculates hashes on every click. **Chosen**: the bulk, single-pass
`run_mutual_audit` call stays exactly as built — computed once, never
recomputed per step. **Why**: a mutual audit is mathematically one verdict
over the whole committed history, not an incremental per-step state —
there is no cryptographically meaningful "verified up to step N, but not
yet step N+1" to recompute into, so redoing the identical deterministic
computation on every button click would be wasted work dressed up as
extra rigor, not real extra verification. The one genuine, actionable gap
the spec surfaced *was* fixed instead: navigation now halts at the first
tampered step (above), which is the real behavior a "no appeal past
disqualification" reading calls for, independent of the recompute-
granularity question.

**A related gap, surfaced the same way, not yet fixed: "TAMPERED" doesn't
by itself become a `TECHNICAL_LOSS`.** A product-style spec for this flow
also states that a mismatch "results in a technical loss." In this repo, a
failed audit never rewrites `Outcome` — by the time
`report_game`/`run_mutual_audit`/`audit_peer` run, the match's `Outcome`
is already fixed (capture, survival, ceiling, or an in-play technical
loss from `play_game`'s own exception handling). What actually happens:
`self_audit_passed`/`peer_audit_passed` are written into the real,
mandatory `ResultBundle` every game reports (`orchestrator_end_of_game.py`)
— tampering is caught and permanently on record — but disqualifying the
match on that basis is left to the human/grader reading the report, not
auto-scored by this code. This matches the book's own "no referee"
design (there is no process with standing to unilaterally overwrite a
peer's own already-computed `Outcome`), but it is a real difference from
that spec's literal wording, so it's recorded here rather than left for a
future reader to rediscover.

**A third contradiction, same shape, in the state machine itself.** A
product-style spec's prose implies the state machine natively transitions
*itself* to `TECHNICAL_LOSS` the instant an illegal target is attempted,
while the book's own `GamePhaseMachine` code sketch and rule 5 both imply
raising an exception instead. **Chosen**: `PeerStateMachine.transition()`
(`planner/state_machine.py`) strictly raises `ValueError` on an illegal
target — it never rewrites its own `.state` to `TECHNICAL_LOSS` itself; an
outer wrapper, `orchestrator_game_loop.py::play_game`'s own
`except Exception` around each `take_turn()` call, catches whatever
propagates and is the one place that formally applies the
`Outcome.TECHNICAL_LOSS` result. **Why**: this exactly matches the book's
own `GamePhaseMachine` code sketch, satisfies rule 5's own wording — the
mandate is to *reject* an illegal move, not silently absorb it, which
`raise` does and a self-mutating `.state` write would not — and still
guarantees the same match-level outcome the spec describes: nothing hangs,
nothing crashes past the boundary, the match safely and deterministically
ends in `TECHNICAL_LOSS` either way.

**A fourth note, on two "resilience" claims and one real gap those claims
surfaced — the gap has since been fixed.** A product-style spec framed the
state machine/deadline/watchdog trio as something that makes *your* agent
"automatically beat any opponent whose agent suffers from unhandled
network errors" and lets you "claim a technical win/draw" when the peer
stalls. Neither is accurate here: `domain/scoring.py::score_outcome`
returns a hard `Score(0, 0)` for every `TECHNICAL_LOSS`, and that is not a
shortcut — `PARAMETERS.md`'s Table 17 row 6 marks `technical_loss: 0` as
**FIXED**, explicitly covering "crash, timeout, cryptographic forgery."
Whichever side's own wait or move computation fails, the score is 0-0 to
both sides; this repo has no mechanism to attribute fault to the *other*
peer and score a win off it (rule 1/2: neither side can see or adjudicate
the other's process). The same spec also claimed the Deadline Tracker
"guarantees your decision computation never exceeds the 30-second... timeout,"
which, before this note, was false — `await_with_deadline` only ever
wrapped waits on the *peer* (`orchestrator_capture.py`, `orchestrator_peer.py`,
`orchestrator_commit_reveal.py`, `orchestrator_step0.py`,
`orchestrator_peer_audit.py`), never `self.brain._decide_move(...)` itself,
which ran as a plain, unbounded synchronous call. **Fixed**: `orchestrator_turn.py::_decide_and_apply_move`
now runs the brain's own decision in a worker thread
(`loop.run_in_executor`) and awaits it through the same `await_with_deadline`
helper, reusing `response_timeout_seconds` — not a new `step_deadline_seconds`
field, since Appendix F defines no separate compute-time budget and I6
forbids inventing an ungrounded quantitative value. A stuck or pathologically
slow brain now raises `DeadlineExceededError` and reaches `TECHNICAL_LOSS`
the same way any other technical loss does, instead of blocking the
process indefinitely; covered by
`test_take_turn_with_a_brain_that_never_finishes_deciding_reaches_technical_loss`
(`tests/unit/test_orchestrator_take_turn.py`). One caveat worth recording
honestly: Python cannot forcibly kill a running thread, so a truly
infinite-looping brain's worker thread keeps existing in the background
even after `take_turn` raises — this bounds how long the *match* waits on
a decision (the real requirement), not how long the OS thread itself
survives.

**A fifth note: why the Deadline Tracker's own "Retry" branch was never
built.** Ch. 8.4.1 describes the Deadline Tracker as, on timeout,
triggering "either a Retry or ... Technical Loss." **The systems risk**:
`_on_reveal_received` applies the peer's hint to the belief map via
`belief_map.update_from_hint` — not idempotent. If a `send_reveal` call
times out because the *response* was slow rather than the request never
arriving, the peer may have already applied it once; a blind retry would
resend the same reveal and the peer would fold the same evidence into its
belief map a second time, corrupting its own Bayesian math. **The choice**:
route every peer-request timeout straight to `TECHNICAL_LOSS` — no retry
branch was added anywhere in this repo's own request/response paths.
**The reasoning**: the book's own wording is "Retry **or** Technical
Loss," not "Retry, then Technical Loss" — Technical Loss alone is a fully
compliant branch on its own, and it's the one that strictly preserves the
Dec-POMDP belief state's mathematical integrity rather than risking a
double-applied update in the name of one more attempt.

`TODO: screenshots — screenshots/live_gui_verified.png,
screenshots/replay_verified_ok.png, screenshots/replay_tampered.png (or
equivalent). These need a human to run the two watch_prd7_*.py scripts
above on a machine with a display and capture the window; that step wasn't
run in this development session.`

## Grading rubric quick-reference

Full detail: `.claude/skills/spec-guard/references/RULES.md` (the 55 binding
rules) and `.claude/skills/spec-guard/references/PARAMETERS.md` (the
mandatory parameter table, Appendix F). `PLAN.md` is the master development
plan; `PRD/` holds the per-layer design documents in build order; `TODO.md`
+ `TODO1.md`–`TODO7.md` hold the corresponding build checklists.
