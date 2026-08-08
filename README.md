# yamanagh-cop

The **cop** peer of a two-peer, judge-free pursuit game — a final project for
*Orchestration of AI Agents*, Dept. of Computer Science, University of Haifa
(spec: book v3.0.0, Dr. Yoram Reuven Segal). This repo contains exactly one
role, cop, never both (rules 1/2); the thief role lives in a separate repo
and runs as a separate OS process. See `CLAUDE.md` for the repo's own
non-negotiable invariants, `PLAN.md` for the full architecture, and `PRD/`
+ `TODO*.md` for the per-layer design/build history.

## Companion (thief) repo

`TODO: real thief-repo GitHub URL — placeholder until the teammate's repo
link is confirmed (rule 49's four cross-links).` `config/game.toml`'s
`[repos]` block holds the negotiated URLs used by the report bundle
(`tools/report_bundle.py`); this line is the human-readable pointer the
README itself is required to carry.

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

**Live GUI** (`observability/live_gui.py::render_state`) renders local
belief only (rules 8/9): exactly three inputs reach the render call — this
side's own `Position`, `BeliefMap._probabilities`, and the current
`PeerStateMachine` state string for the turn banner. It never receives
`GameState.target_pos` or the true opponent position — this repo's own
`Orchestrator` never even holds that value (rule 1/2). Enforced by
introspecting `render_state`'s own parameter list
(`test_render_state_signature_admits_no_true_opponent_position_or_board`),
not by inspecting a screenshot. Demoed live end-to-end by
`scripts/watch_prd7_live_gui.py`.

**Replay App** (`observability/replay_viewer.py::ReplayViewer`) reads a
recorded `log_<game_id>_g<NN>.json`, steps through it, and stamps
`Verified OK` / `TAMPERED` by wrapping the real
`integrity/audit.py::run_mutual_audit` — never a simplified sketch of the
audit logic. Demoed live, both the honest path (`Verified OK`) and the
adversarial path (a tampered log correctly flagged `TAMPERED`), by
`scripts/watch_prd7_replay.py`.

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
