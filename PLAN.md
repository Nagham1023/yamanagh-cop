# PLAN.md — Distributed Cops-and-Robbers over a Peer-to-Peer Network

Master development plan. This file satisfies the mandatory `PLAN` artifact of rule 50 and is the parent document for the seven PRDs.

- **Course:** Orchestration of AI Agents, Dept. of Computer Science, University of Haifa
- **Spec:** book v3.0.0, Dr. Yoram Reuven Segal
- **Sole source of numeric truth:** Appendix F → `.claude/skills/spec-guard/references/PARAMETERS.md`
- **Binding rules:** Appendix E → `.claude/skills/spec-guard/references/RULES.md`

---

## 1. What we are building

Two autonomous agents — a **cop** and a **thief** — that play a pursuit game on a discrete grid against an agent built by another team, on another machine, across the public internet, **with no central server and no referee**.

Neither agent observes the true world state. Each builds a belief about its opponent's position from two channels: a decaying scent field, and a short natural-language hint that the sender is permitted to falsify. The system is modelled as a **Dec-POMDP** and runs over **MCP** (via FastMCP), where each agent is simultaneously server and client.

Because there is no judge, integrity is established mathematically — a **SHA-256 Commit-Reveal** protocol plus a full mutual log audit at the end of every game.

### The four metrics we are graded on

The book is explicit that no single elegant algorithm wins this. Success is measured on:

1. **Coordination** — the two agents interoperate correctly under a shared contract.
2. **Adaptation under uncertainty** — stigmergic scent trails converted into usable probability.
3. **Integrity** — cryptographic guarantees that hold under adversarial audit.
4. **Architecture** — correct use of the Orchestrator and Gatekeeper patterns.

Design decisions throughout this plan are made in service of those four, not in service of winning any individual match.

---

## 2. Why this is orchestration, and what that obliges us to build

Book §1.2.1 draws a sharp line between two things that are easy to confuse:

- **Prompt chaining** — piping one model's output into the next along a fixed linear sequence. No dynamic division of labour, no bidirectional context sharing, no shared state. **This is not orchestration.**
- **Multi-agent orchestration** — *distributed* management of division of labour, context sharing, and system state between agents running in parallel. **This is the model the project adopts.**

The agents running in parallel are the two peers. §1.3 fixes **n = 2** in the Dec-POMDP tuple: cop and thief. There is no third agent and no supervisor — the "distributed" in that definition is the whole point, because a supervisor would be the referee the project exists to eliminate.

This matters practically, because the book names **three failure modes that afflict multi-agent systems lacking a real orchestration layer** — and each one has a concrete form in this project, and a mandatory rule that exists to prevent it.

| Failure mode | Its form here | Mechanism that prevents it | Rules |
|---|---|---|---|
| **Contradictory outputs** — agents reach opposing conclusions with no deciding mechanism | The two teams disagree on who won | Commit-Reveal plus the end-of-game mutual log audit **is** the deciding mechanism. An unresolved contradiction voids the game for **both** sides — it is treated as a system failure, not a dispute to be arbitrated. | 19, 35, 36 |
| **Convergence failure / infinite loops** — mutual response loops that never halt | Both peers blocked waiting on the other; turn-scheduling deadlock | Deadline tracker on every wait; watchdog supervising the process; a state machine that refuses illegal transitions instead of spinning | 4, 5, 6, 7 |
| **Task duplication** — redundant work burning compute and token budget | Repeated LLM calls, recomputed inference across turns | Token budget declared and reported; efficiency normalized into the league grade; `template` mode as the zero-token default | 54, Table 18 |

Read this way, rules 4–7, 19 and 35 stop being compliance overhead and become the orchestration layer itself. That framing belongs in the academic README — connecting the chapter 1 formalism to specific architectural decisions is directly what the **architecture** metric rewards.

Two consequences for how we build:

1. **We do not add game-playing agents.** `n = 2` is fixed by the formalism. No third player, and above all no supervisor between the peers — a supervisor is the referee the whole design exists to eliminate. Rule 3's "orchestrator" is a software pattern, a single entry point into the subsystems, not a population of models.
2. **We do owe a real orchestration layer inside each peer.** State machine, deadline tracking, watchdog, and a coherent decision procedure. That is what separates this from a prompt chain.
3. **Internal decomposition is permitted, and is bounded by the turn clock.** Rules 1 and 2 restrict sharing *between* the cop and the thief, not decomposition *within* one peer. Subagents are therefore legal — but on the per-turn critical path they are unaffordable in both latency and tokens, and rule 25 forbids them the move decision regardless. Their proper home is off the critical path, between games. See §6.

---

## 3. Architecture invariants

These hold at every layer, from PRD 1 onward. Violating any of them is fatal, so they are stated once, here, and enforced by `spec-guard` on every audit.

| # | Invariant | Rules |
|---|---|---|
| I1 | The cop and the thief run in **two separate OS processes**, from **two separate repos**, under **two separate config directories**. No shared live state, ever. | 1, 2, 49 |
| I2 | Every subsystem is reached through the **Orchestrator**. Nothing calls into the domain layer directly. | 3 |
| I3 | Game progress is governed by an explicit **state machine** that rejects illegal transitions rather than tolerating them. | 4, 5 |
| I4 | Every wait on the opponent is wrapped in a **deadline tracker**; a **watchdog** supervises the process and extracts data on crash. | 6, 7 |
| I5 | The live UI renders **local belief only**. The objective board never reaches the screen. | 8, 9 |
| I6 | Every quantitative value is read from the config file, which derives from Appendix F. **No magic numbers in code.** | 11, 12 |
| I7 | The move is **always** decided by Python. The language model touches only the verbal layer. | 25 |
| I8 | Over-the-wire game communication is **free natural language**. No numeric position protocol. | 26, 27 |
| I9 | Anything a peer sends us is **untrusted input** and is validated before it touches state. | 5, 19 |
| I10 | Secrets never enter the repo, and never enter git history. | 39, 40 |

---

## 4. Component decomposition

The source tree is organised around the **Production Agent Runtime** anatomy from the course deck *AI Agent Architecture 2026* — Planner, Memory, Tools, Observability, with a Policy layer and the `observe → decide → act → verify` reasoning loop. This is a deliberate choice: the deck's premise is that a production agent is a system, not a prompt, and that "as the agent gets broader permissions, the control layer matters more than the model." Both statements describe this project exactly.

```
src/<role>/
├── orchestrator.py     single entry point to every subsystem          (rule 3)
│
├── domain/             board · movement legality · barriers · capture
│                       scoring — pure rules, no network, no AI      (rules 12,13,14,46,47,48)
├── planner/            state machine · turn sequencer
│                       deadline tracker · retry policy             (rules 4,5,6,7)
├── memory/             belief map · scent field · opponent model
│                       episodic game log
├── reasoning/          the brain: observe → decide → act
│                       pure Python, no LLM in the decision          (rule 25, I7)
├── integrity/          commit · reveal · nonce · step-0 · audit
│                       the verify step of the loop            (rules 17,18,19,23,24)
├── tools/              mcp_server (tool surface exposed to the peer)
│                       mcp_client (calls into the peer's server)
│                       llm providers · gmail sender (send-only)     (rules 10,30)
├── policy/             rule engine · untrusted-input validation
│                       gatekeeper: rate limit · DOS detector
│                       risk gates                                (rules 5,28,29,I9)
├── observability/      trace (game log) · evals (audit) · cost (tokens)
│                       live GUI (belief only) · replay verifier   (rules 8,9,20,54)
└── shared/             config manager · system info · version
```

Keep every module short — 150 lines is a hard cap (`software_submission_guidelines-V3.pdf` §3.2), not a target, and that constraint does real work for readability and testability. When a file grows past it, split it: extract a shared helper into its own module, extract a mixin, do a 50/50 read/write split, or extract constants/models into their own file.

### Mapping to the 2026 architecture

| Deck concept | Here | Note |
|---|---|---|
| **Planner** — decompose · sequence · retry | `planner/` | The turn sequencer and state machine. The deck's point that a branching, resumable workflow needs a state machine rather than a chain is rules 4 and 5. |
| **Memory** — state · history · context | `memory/` | The Dec-POMDP belief state. Scent field, belief heatmap, opponent model, game log. |
| **Tools** — APIs · files · DB | `tools/` | The MCP surface exposed to the opponent, plus the client that calls theirs. |
| **Observability** — trace · evals · cost · audit | `observability/` | Trace = the game log; evals = the mutual audit; cost = token totals (rule 54). |
| **Reasoning loop** — observe → decide → act → verify | `memory/` → `reasoning/` → `tools/` → `integrity/` | Observe scent and hint, decide in Python, act by committing and moving, verify by audit. The loop maps one-to-one. |
| **Policy layer** — guardrails · permissions · audit trail | `policy/` | The Gatekeeper parameters of Table 19 are exactly this layer. |
| **Human-in-the-loop gate** | §8 checkpoints | Config negotiation, secret handling, milestone observation. |

### Reconciling with the Professional Software Guide

`software_submission_guidelines-V3.pdf` mandates two things this tree needs to answer explicitly, not leave implicit:

1. **SDK architecture (guide §4.1, §17.2, §20.9).** The guide requires all business logic reachable through a single `sdk.py` facade. `orchestrator.py` (rule 3, I2) *is* that facade for this project — it is already the single entry point every external consumer (GUI, CLI, MCP tool handlers) goes through. No separate `sdk.py` is needed; the submission checklist's "SDK architecture" line is satisfied by `orchestrator.py`, and the academic README should say so explicitly rather than leaving a grader to guess.
2. **Gatekeeper numeric precedence.** The guide's illustrative `ApiGatekeeper` config (§5.2: `concurrent_max: 5`, `retry_after_seconds: 30`) does not match Table 19 (`concurrent_requests: 2`, `retry_backoff_sec: 5` — Appendix B's actual nested field names, `todoFullFix.md` §A). Table 19 is a locked MINIMUM under Appendix F and wins for every value it defines — the guide's numbers are illustrating the pattern's *shape* (the `execute()` / `get_queue_status()` interface, queue-and-retry behaviour), not proposing different values for this project. `policy/gatekeeper.py` must expose that interface shape while reading its numeric limits from the negotiated config's `rate_limiter_gatekeeper` block (`config/shared/config_<game_id>_g<NN>.json`).

### Two honest deviations, both worth documenting

**1. We use MCP horizontally, where the 2026 map would use A2A.** The deck separates *vertical* integration (MCP: agent ↔ tools and data) from *horizontal* interoperability (A2A: agent ↔ agent, task delegation and lifecycle). This project mandates MCP for peer-to-peer communication — a horizontal use of a vertical protocol. Book §2.3 acknowledges the gap by recommending A2A as a complementary standard for task lifecycle management between agents. **The rulebook wins: we use MCP.** But naming the tension shows we understood both.

**2. The reference repo uses a different tree** (`ui / sdk / runtime / domain / infra / shared`). Only rule 50's artifacts are mandatory — README, `config/`, PRD files, PLAN, TODO — so the source layout is ours to choose. The cost of deviating is friction when borrowing code from the reference implementation. The benefit is a structure that argues for itself.

**3. `PLAN.md` and `TODO.md` live at repo root, not under `docs/`.** The Professional Software Guide (§2.2) wants `docs/PRD.md`, `docs/PLAN.md`, `docs/TODO.md`. Rule 50 only requires these files to exist somewhere in the repo, not at a specific path, so we keep `PLAN.md`/`TODO.md` at root (where `spec-guard` and the rest of this project's tooling already expect them) and put PRD files under `PRD/` rather than `docs/`. This is a deviation from the guide's literal path, not from its intent — both files exist, are current, and are linked from the README, which is what the guide's checklist (§20.9) actually checks for.

### Security model: this project *is* the OWASP agentic threat map

The deck cites *OWASP Top 10 for Agentic Applications 2026* and names four risks. Each has a direct form here — and one of them is not a risk at all, it's the game:

| OWASP agentic risk | Its form in this project | Defence |
|---|---|---|
| **Memory poisoning** — false data injected into memory, corrupting future decisions | **This is the core game mechanic.** The opponent's verbal hint is a deliberate attempt to poison your belief map. | Bayesian weighting; corroborate every hint against the scent field, which cannot be faked; the learned deception prior from §6 |
| **Goal hijacking** — manipulating the agent's objective through input | A crafted hint designed to pull the strategy off its objective rather than merely mislead about position | The move is decided in pure Python from the belief map (rule 25). Text can never reach the objective function. |
| **Tool misuse** — an authorised capability invoked to cause harm | The peer calling our MCP tools out of order, or with payloads designed to corrupt state | The state machine rejects illegal transitions (rule 5); all peer input is untrusted until validated (I9) |
| **Identity abuse** — misuse of identity, permissions or access tokens | A forged move attributed to us; a replayed old commitment | Commit-Reveal binds each commitment to `State`, so a stale commitment cannot be reused; audit catches any mismatch (rules 17, 19) |

The deck's control triad applies directly: **control** through least privilege and scoped tools (Gmail send-only, rule 30); **detection** through trace logging and policy evaluation (the game log and the audit); **recovery** through audit replay (the Replay app, rule 20).

That the scent channel is *uncorruptible* while the verbal channel is *freely corruptible* is the sharpest design fact in the project. An agent cannot plant a false trail somewhere it has not been — it can only strengthen the scent where it actually stands, which helps its opponent. Deception is confined entirely to language. That asymmetry is what makes a Bayesian belief map beat a credulous one.

**The two student extension points**, both selected in the *private* config and never negotiated:

- `[strategy] police_class` / `thief_class` → your brain, inheriting `BrainBase`, overriding `_pick_move` (and `_decide_move` for the cop, where the barrier choice is made). **This is where the grade lives.**
- `[trash_talk] provider` → how the deception text is produced. Default `template`, zero tokens.

### The state machine

Explicit states, with every other transition rejected (I3):

```
INIT
  → NEGOTIATING            agree the shared contract with the opponent
  → CONFIG_LOCKED          config hashed and locked; byte-identical confirmed
  → STEP0_DECLARED         hardware + LLM + token budget + commit hash signed
  → TURN_START        ┐
  → COMMITTED         │    our sealed hash sent
  → PEER_COMMITTED    │    their sealed hash received
  → ACKNOWLEDGED      │    both sides locked
  → REVEALED          │    move + hint exchanged (nonce still secret)
  → TURN_RESOLVED     ┘    physics applied, scent decayed, belief updated
  → GAME_OVER              capture, survival threshold, or technical loss
  → FINAL_REVEAL           all nonces released
  → AUDITED                every hash recomputed and compared
  → REPORTED               JSON sent by both teams, results agreed
```

`GAME_OVER` is reachable from any state via the technical-loss path (crash, timeout, forgery). That path must still produce a log and a report — a crashed game with no record is worse than a lost one.

---

## 5. The seven layers

One PRD per layer. **Build strictly in order.** The reason is diagnostic, not ceremonial: if encryption sits on networking that was never proven, a lost message could be the crypto, the transport, or the game logic, and a one-variable investigation becomes an unsolvable three-variable one.

A layer is finished when its milestone is **observed end-to-end**, not when its code is written.

### PRD 1 — Base logic

**Build:** the grid, the movement set, barrier placement and quota, capture detection, scoring, the end conditions. Single process, no network, no AI, no crypto.

**Explicitly out of scope:** two processes or MCP of any kind (PRD 2); a strategy module, heuristics, or Q-learning (PRD 3); natural language, scent, hints, or an LLM call of any kind (PRD 4); ngrok/tunneling (PRD 5); Commit-Reveal, nonces, hashing, or Step-0 (PRD 6); the GUI, Replay app, Gmail, or the Gatekeeper (PRD 7). If it touches a network socket, a cryptographic primitive, or a language model, it does not belong in this layer, full stop — that boundary is what makes the next layer's bugs isolable.

**Rules owned:** 12, 13, 14, 46, 47, 48, and I6.

**Milestone:** two agents move legally on a `[board size]` grid; a barrier beyond `[barrier quota]` is rejected; coordinate overlap triggers a capture.

**Also verify:** a barrier dropped on the thief's own cell registers as a capture (46); a thief with zero legal moves registers as captured (47); the cop cannot place a barrier further than one cell away, or off the board edge; a diagonal is rejected; all three end-of-subgame outcomes (capture, survival, technical loss) score correctly against Table 17's five parameter values.

**Done when:** `pytest` covers every rule above, and `check_config.py` passes on the config the tests load.

---

### PRD 2 — FastMCP infrastructure over localhost

**Build:** split into two processes. Stand up each peer's FastMCP server, define the tool surface, connect each peer's client to the other's server. Introduce the Orchestrator, the state machine, the deadline tracker and the watchdog.

**Messages at this stage carry bare coordinates** — this is the one and only point in the project where that is legal, because the language layer does not yet exist. It must be removed in PRD 4 (rule 27).

**Rules owned:** 1, 2, 3, 4, 5, 6, 7.

**Milestone:** a geometric message leaving agent A over localhost is received and correctly decoded by agent B.

**Also verify:** an illegal state transition is rejected rather than absorbed; killing one peer causes the other to hit its deadline and exit cleanly with a log rather than hanging; the watchdog fires and extracts data on a forced crash; the two processes share no importable live state.

---

### PRD 3 — Blind strategy

**Build:** the first real brain, operating in a world of **perfect information**. Heuristic distance (Manhattan), your own algorithm, or optionally Bellman/Q-learning. "Blind" means blind to uncertainty — there is no scent, no language and no deception yet.

**Rules owned:** 25, and the `BrainBase` extension contract.

**Milestone:** given a known target position, the agent computes and executes the shortest path with no manual intervention.

**Also verify:** the cop's barrier policy never walls the cop off from the thief; the thief prefers cells with more escape routes; both respect the step ceiling.

**Note:** the course did not teach reinforcement learning, and the book states plainly that a fully competitive agent can be built from heuristics alone. Treat RL as optional and only if time permits after PRD 7.

**Rule 25's negotiated exception (`todoFullFix.md` §F, ch. 6.5 p.65-66), verbatim:** "as part of the negotiable rule system, both sides may agree in advance — in the negotiation stage before the game — to allow an LLM-based tactic to also influence the move decision, instead of exclusive reliance on the algorithm... not valid unless explicitly and mutually agreed, documented between the groups; one side may not unilaterally adopt such tactic... the local algorithm must still enforce move legality and reject any illegal move the model proposes." Documentation only — this repo does not currently exercise the exception: `CopBrain`/`_pick_move`/`_decide_move` stay algorithmic-only by default, exactly as `PLAN.md`'s own default and the book's own recommended posture both already are. Adopting the exception later would need the same explicit, written, mutual agreement `WIRE-CONTRACT.md` already requires for everything else negotiated between the two repos — not something either side introduces unilaterally by just wiring an LLM into its own `_decide_move`.

---

### PRD 4 — Language and scent

The step change, and the most delicate layer in the project.

**Build:** replace the coordinate messages with free natural language for the tactical hint. Implement pheromone emission and decay. Build the Bayesian belief heatmap, fed from two channels — the natural-language hint (rule 26/27, may lie) and a separate Tool-call data channel exposing the opponent's own scent field as structured numeric data (ch. 6.4/6.5 — PRD 4 "Revision 3," `todoFullFix.md` §C; not natural language, and not the same channel as the hint). Wire in the LLM for hint generation, including the `Intent` truth/lie flag.

**Rules owned:** 23, 26, 27, plus Tables 14 and 16.

**Milestone:** a known-false hint measurably shifts the belief map in the wrong direction, while the scent map keeps decaying correctly underneath it — i.e. the two channels are observably independent and the deception channel is actually being exercised, not just present.

**Also verify:** no coordinates survive anywhere in the outgoing hint (grep the wire, do not trust inspection); hints respect `[hint word limit]`; scent constants match Table 16 exactly and are exposed for pre-game locking; the belief map is a genuine probability distribution that sums to one; a known-false hint measurably shifts belief in the wrong direction, proving the channel is actually being used.

**Design question to answer in the PRD, not in code:** how much weight does a verbal hint carry against a scent gradient, and how does that weight change as the opponent's hints prove reliable or unreliable over the course of a game? This is the intellectual core of the project and the single largest differentiator in the grade.

---

### PRD 5 — Cloud exposure and tunneling

**Build:** move off localhost. Expose each FastMCP server through ngrok or Localtonet. Handle latency, disconnection and reconnection.

**Rules owned:** 10, and hardening of 6 and 7 under real network conditions.

**Milestone:** an agent on a genuinely remote machine — a different network, not just a second process on the same laptop — connects via ngrok and plays a full round against the local agent. Confirm by reading the opponent's IP out of the connection logs: it must not be `127.0.0.1` or a LAN-local (`192.168.x.x` / `10.x.x.x`) address.

**Also verify:** a mid-game tunnel drop produces a clean technical loss with an intact log, not a hang and not a crash.

---

### PRD 6 — Security and cryptography

**Build:** Commit-Reveal over SHA-256. The nonce generator. The four-phase exchange. The Step-0 declaration. The cryptographic locking of the negotiated config, including the byte-identity check against the opponent's copy. The end-of-game mutual audit.

**Rules owned:** 11, 17, 18, 19, 21, 22, 24, 53, and the enforcement half of 15, 16.

**Milestone:** a move is committed and then revealed with a valid nonce; Step-0 verifies hardware.

**Also verify:** the SHA-256 of our locked config matches the opponent's, byte for byte, before the first move (`check_config.py --identical`); nonces come from `secrets`, never `random`; the commit payload is canonical JSON (`sort_keys=True, separators=(",", ":")`) so both peers hash identical bytes; the nonce is not transmitted until the final reveal; hash comparison uses `secrets.compare_digest`; a deliberately tampered log **fails** the audit — write that test, because a verifier that never rejects anything is worthless; Step-0 carries the exact commit hash being played.

**Closed at PRD 6 (built, not just flagged):** "Rules owned" above lists 15/16/21/22 — as of PRD 5 there was no wire channel at all for either, `tools/mcp_server.py`'s surface being only `receive_hint(text)` and `share_scent_map()` (PRD 4 "Revision 3"). PRD 6 added `receive_barrier_declaration` and `receive_capture_claim`/`receive_capture_response` (`tools/mcp_server_prd6.py`, `integrity/capture_protocol.py`), folded into that turn's own commit — see `PRD-6-security-and-cryptography.md` for the full build and retrospective.

**A second, more urgent flag from the same hardening pass:** none of the *existing* wire surface has ever been negotiated with the thief repo either — `WIRE-CONTRACT.md` (repo root) is where that negotiation is supposed to happen, and as of this writing it hasn't. Ch. 3.2's "shared contract" discipline (config/game.json, "fixed before the exchange begins... mutually agreed by both sides") has only ever been applied to game *rules* in this repo, never to the MCP tool schema itself — and the book's own `receive_move` example (ch. 2.3) is explicitly illustrative, not a fixed standard, so nothing forces two independently-built teams to converge on the same shape by accident. Every one of PRD 6's new tools (barrier declaration, capture claim/response, commit/reveal) inherits this same gap the moment it's built. Send `WIRE-CONTRACT.md` to the teammate and get it confirmed *before* extending it with PRD 6's new tools, not after.

---

### PRD 7 — Reporting and visualization shell

**Build:** the live GUI, the Replay/verifier app, Gmail over OAuth 2.0 with send-only scope, the token-bucket rate limiter, the DOS detector, the JSON report. The pre-game declaration and the final result report use Table 20's own naming exactly: `declaration_<game_id>.json` and `result_<game_id>.json` (`todoFullFix.md` §G, `PARAMETERS.md`'s Table 20) — don't invent a different name for either when this layer starts.

**Rules owned:** 8, 9, 20, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 41, 42, 43, 44, 45, 49, 50, 51, 52, 54, 55, 39, 40.

**Milestone:** a game summary is sent by Gmail; the GUI displays the state; the Replay app reconstructs a recorded round.

**Also verify:** the GUI cannot render the opponent's true position — check this by reading what data reaches the render call, not by looking at the screen; the Replay app displays `Verified OK` on a clean log and **rejects** a tampered one; the report is an attached JSON file, never body text; token totals and commit hash are present; `.gitignore` covers `credentials.json`, `token.json` and `.env`, and `git log --all --full-history` finds no trace of them.

**Research-and-analysis deliverables (Professional Software Guide §9, §11; submission checklist §20.9 items 5/7).** The book's rules don't ask for these, the guide does — bolt them onto PRD 7 rather than inventing an eighth mandatory layer:

- A results-analysis notebook (`notebooks/` or `docs/`) that reads the recorded game logs and renders belief-map heatmaps, a scent-decay curve, and a win/loss/technical-loss breakdown across the counted games.
- One parameter-sensitivity pass: hold everything else fixed and vary the belief-weighting between scent and hint (the design question PRD 4 flags as "the intellectual core of the project") across a handful of warm-up games, and plot the effect on capture rate.
- A token-cost breakdown table (model, input/output tokens, estimated cost) sourced from the same totals already required in the final JSON report (rule 54) — this is a formatting pass on data the project already collects, not new instrumentation.

---

## 6. Optional layer 8 — orchestrated between-game learning

**Status: optional. Build only after PRD 7 is running.** An elegant learning system attached to an agent that cannot finish a game is worth nothing, because revealed logs are its entire input.

### Why this sits off the critical path

The per-turn loop runs under a 30 s response timeout and a 60 s watchdog. A coordinator that decomposes, dispatches, waits and aggregates costs four or more LLM round-trips per turn; overrunning the deadline is a technical loss and zero for both sides (rule 6). The arithmetic compounds: 6 sub-games × 35 steps ≈ **210 turns per opponent** against a ~200,000 token budget, with efficiency normalized into the grade. And rule 25 means the coordinator could never own the move anyway.

So: **deterministic Python during play, orchestration between games.**

### The opportunity

A series is **six sub-games against the same opponent**. The final reveal of each sub-game exposes every nonce **and every `Intent` flag** — giving ground truth on whether each of their hints was a lie. After sub-game 1 you hold a labelled dataset of that specific opponent's deception behaviour, usable in sub-games 2 through 6. Very few teams will exploit this.

### Build in three rungs

Each rung is useful alone, so running short of time costs the next rung rather than the whole feature.

1. **Deterministic baseline (~20 lines).** Compute the opponent's lie rate from revealed `Intent` flags, and whether it shifts when they are cornered. Feed it into hint-weighting for the next sub-game. No agents involved.
2. **Coordinator + subagents.** Richer profiling, report generation, documentation, with a `spec-guard` auditor subagent checking the others' output.
3. **Refinement loop.** Coordinator evaluates synthesis for gaps and re-delegates until coverage is sufficient — see the termination rule below.

### Coordinator responsibilities

Four responsibilities define the coordinator. Each is stated here in its general form and then in the concrete form it takes in this project.

**1. Dynamic subagent selection.** The coordinator analyses the requirements of the incoming task and selects *which* subagents to invoke. It does **not** always route through the full pipeline — a simple factual query might need only a search subagent, not the whole research → analysis → synthesis chain. Routing every query through every subagent wastes time and resources.

> *Here:* after a clean sub-game with no anomalies, invoke the deception profiler only. If the opponent never lied, skip deception-model refinement entirely. Invoke the movement profiler only when their barrier or evasion pattern changed materially. Invoke report generation once per series, and documentation only at milestone or submission time. A fixed pipeline that runs everything after every sub-game is the failure this responsibility exists to prevent.

**2. Research scope partitioning.** When delegating to multiple subagents, the coordinator partitions the scope so that work is not duplicated, assigning distinct subtopics or source types to each agent — one searches academic papers while another searches news, rather than both searching the same sources.

> *Here:* partition by artifact and by question. One subagent reads the `Intent`/hint stream and answers *do they lie, when, and how often*. Another reads the move and barrier stream and answers *how do they behave when cornered*. A third reads the Step-0 declaration and timing data and answers *what are their compute and latency constraints*. Non-overlapping inputs, non-overlapping questions. Two subagents reading the same log slice is the anti-pattern.

**3. Iterative refinement loops.** The coordinator evaluates synthesis output for gaps. Where synthesis is incomplete, it re-delegates to the search and analysis subagents with **targeted** queries, and re-invokes synthesis until coverage is sufficient. This is a cycle, not a single shot.

> *Here:* if the synthesized opponent model has no evidence for behaviour under enclosure — say they were never cornered in sub-game 1 — the coordinator re-delegates a targeted query against later logs rather than re-running the whole profile. Synthesis is re-invoked until the model covers the situations that actually matter for move selection.

**4. Centralised communication routing.** All subagent communication routes **through** the coordinator, giving observability, consistent error handling, and controlled information flow. Subagents do not talk to each other directly.

> *Here:* this is rule 3 at the agent level — the coordinator is the single entry point, exactly as the Orchestrator is for the subsystems. It also means every subagent invocation and every token spent is logged in one place, which is what makes the token totals in the final report (rule 54) accurate rather than estimated.

### Designing against the three failure modes

The failure modes from §2 become this layer's own risk register. Documenting how the design defends against each is precisely what the **architecture** metric rewards.

| Failure mode | How it would appear here | Defence |
|---|---|---|
| **Task duplication** | Two subagents profiling the same log slice; the full pipeline re-run after every sub-game | Responsibilities 1 and 2 — dynamic selection and scope partitioning |
| **Contradictory outputs** | The deception profiler and the movement profiler imply opposite beliefs, with nothing to arbitrate | Responsibility 4 — the coordinator is the single deciding point; conflicts resolve there, never between subagents |
| **Convergence failure** | The refinement loop never terminates, re-delegating on output it keeps judging insufficient | **Bound it explicitly.** See below. |

**The refinement loop must be bounded, and this is not optional.** Responsibility 3 is the one that *causes* convergence failure if left open. Ship it with all three of:

- a **hard iteration cap** (e.g. 3 refinement rounds), after which the current synthesis is accepted as-is;
- an explicit **coverage criterion** that decides "sufficient" as a checkable condition, not a judgement call;
- a **wall-clock budget** for the whole between-game phase, so a stuck loop cannot delay the next sub-game.

A refinement loop with no termination proof is the textbook case the book warns about — and the loop returning a merely adequate model is always cheaper than the loop not returning.

### Milestone

After a completed series, the coordinator produces an opponent model derived from revealed logs; that model measurably changes hint-weighting in the next sub-game; the refinement loop terminates within its cap on every run; and every subagent invocation appears in a single coordinator-owned log with its token cost.

### For the README

Write up: which subagents exist and why each earns its place; the selection rule that decides when each is skipped; the partitioning scheme and why the slices do not overlap; the termination criteria for the refinement loop; and the routing topology. That write-up, connected back to §2, is the strongest architecture evidence in the project.

---

## 7. Repository layout

Two repos (rule 49), cross-linked in both READMEs. Each contains at minimum README, `config/`, PRD files, PLAN and TODO files (rule 50).

```
<team>-cop/                          and    <team>-thief/
├── README.md                        ← the academic report lives here   (rule 42)
├── CLAUDE.md                        ← auto-loaded context for Claude Code
├── PLAN.md                          ← this file                        (rule 50)
├── TODO.md                          ← running state                    (rule 50)
├── FULLFIX.md / todoFullFix.md      ← cross-cutting correction pass, five foundational findings — rationale + 150+-item checklist
├── WIRE-CONTRACT.md                 ← MCP tool schema, negotiated with the opponent team — send this, not just config/shared/config_<game_id>_g<NN>.json
├── .gitignore                       ← credentials.json, token.json, .env (rules 39,40)
│
├── PRD/                                                                (rule 50)
│   ├── PRD-1-base-logic.md
│   ├── ...
│   ├── PRD-7-reporting-shell.md
│   └── PRD-8-coordinator.md         ← optional, §6
│
├── .claude/
│   ├── agents/
│   │   ├── rule-auditor.md          ← audits each layer against spec-guard
│   │   └── adversary.md             ← hostile peer simulator, from PRD 5
│   └── skills/spec-guard/
│       ├── SKILL.md
│       ├── references/  RULES.md · PARAMETERS.md
│       └── scripts/     check_config.py
│
├── config/                                                             (rule 50)
│   ├── shared/   config_<game_id>_g<NN>.json   ← negotiated, locked, committed
│   └── game.toml                                ← private, TOML, six sections incl. [network].opponent_url — hand-edited, never negotiated, never crosses the network (Appendix B, todoFullFix.md §B)
│
├── src/<role>/
│   ├── orchestrator.py              single entry point                 (rule 3)
│   ├── domain/                      board · movement · barriers · capture · scoring
│   ├── planner/                     state machine · sequencer · deadlines · retry
│   ├── memory/                      belief · scent · opponent model · episodic log
│   ├── reasoning/                   observe → decide → act  (pure Python)
│   ├── integrity/                   commit · reveal · nonce · step-0 · audit
│   ├── tools/                       mcp_server · mcp_client · llm · gmail
│   ├── policy/                      rules · validation · gatekeeper · risk gates
│   ├── observability/               trace · evals · cost · gui · replay
│   └── shared/                      config · sysinfo · version
│
├── tests/                           mirrors src/, one rejection test per layer
├── logs/    log_<game_id>_g<NN>.json          ← needed for replay and audit (rule 20)
├── declaration_<game_id>.json       ← pre-game declaration: teams, members, repos, hardware, model, tokens, times (Table 20 — PRD 7 territory, not built yet)
├── result_<game_id>.json            ← final result report the lecturer weights the league score by (Table 20 — PRD 7 territory, not built yet)
└── docs/    belief-map and "Verified OK" screenshots                    (rule 42)
```

Config files are named per game so any match is reproducible, and every game's config is committed (Appendix F mandatory rules 3 and 4). Table 20's full four-file naming convention (`todoFullFix.md` §G): `declaration_<game_id>.json`, `config_<game_id>_g<NN>.json`, `log_<game_id>_g<NN>.json`, `result_<game_id>.json` — the config name already matches what this repo uses (`config_dev_g01.json`); the log name does **not** yet — `Orchestrator.__init__`'s actual default is `log_path: str = "logs/trace.jsonl"`, confirmed directly against the source, not `logs/log_<game_id>_g<NN>.json` (found and corrected during PRD 7's own critique pass, `log_path` is already a constructor parameter, so a real game's own end-of-game orchestration just needs to pass the correctly-formatted path explicitly, not a code change here). `declaration_`/`result_` don't exist yet (PRD 7's job), recorded here now so the correct name is on record before that layer starts, not reinvented then.

`src/<role>/` means `src/cop/` in one repo and `src/thief/` in the other — **one role per repo**, so there is no directory from which both could ever be imported together (rules 1, 2).

---

## 8. Development discipline

**Definition of done for a layer.** All six, in order:

1. The milestone behaviour has been **watched end-to-end by a human**.
2. `pytest` passes, including at least one test that proves the layer **rejects** bad input, at ≥85% coverage on the code touched (`software_submission_guidelines-V3.pdf` §6.2).
3. `ruff check` passes with zero violations on the code touched (`software_submission_guidelines-V3.pdf` §7.1).
4. `spec-guard` Mode 1 reports no violations among the rules that layer owns.
5. Every new function, class, and module has a docstring (house rule, CLAUDE.md).
6. Committed, with the PRD updated to record anything that changed during implementation.

**Where the human must hold the wheel.** Let Claude Code work freely at PRDs 1–3. Take over at these six points, where being wrong is either unrecoverable or invisible:

| Checkpoint | Why |
|---|---|
| Negotiating the shared config with the opposing team | A human agreement. Must end byte-identical or the game is void. |
| Writing and verifying `.gitignore` | A leaked credential is permanent. Verify against git history, not the file tree. |
| Hand-checking one commit hash | A commit-reveal with a weak nonce runs perfectly and protects nothing. |
| The belief-vs-hint weighting design | The graded core. Claude should implement your reasoning, not invent it. |
| Every milestone gate | "It should work now" is not an observation. |
| Reading the final JSON before the first counted game | Rule 35 zeroes **both** teams on a contradictory report. |

---

## 9. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Coordinate protocol from PRD 2 left in place after PRD 4 | Fatal (27) | Explicit removal task in PRD 4; grep the wire before the first real game. |
| Nonce from `random`, or leaked per-turn | Fatal (18) | `spec-guard` code audit; hand-verify once. |
| Config differs by whitespace or key order | Fatal (11) | `check_config.py --identical` before every game. |
| GUI leaks the true board | Fatal (8, 9) | Audit the data path into the renderer, not the visual output. |
| Secret committed early, discovered late | Fatal (39) | `.gitignore` before the first commit; history sweep before submission. |
| Opponent's report contradicts ours | Fatal for **both** (35) | Complete the mutual audit and agree the result *before* either side sends. |
| Token budget exhausted mid-series | Lost games | Default to `template` mode; `every_n_steps`; the efficiency bonus rewards this anyway. |
| Skipping a layer to reach the "interesting" parts | Schedule collapse | The layer order is the plan; deviation is a decision that gets written down. |

### Where the margin actually is

- **Efficiency is normalized into the grade.** A lean agent on a modest laptop that beats a heavy one scores *better*, explicitly. `template` mode plays a full six-sub-game series at zero tokens, which throws the whole contest onto movement quality — where we want it.
- **Diversity reward is 10 points per win against a new opponent**, with one counted game per opponent and a cap of 10 games. Playing more distinct teams is directly worth points, and warm-up games do not count against the cap.
- **Barriers are the cop's entire game.** Fourteen permanent walls, with an instant capture available by dropping one on the thief's cell or by sealing its last exit. Most teams will treat barriers as an afterthought to chasing.
- **Discipline in the small things** is where teams die — not in the strategy. Every fatal rule on the list is trivially avoidable and completely invisible until the audit.

---

## 10. Sequence

1. `spec-guard` installed in both repos. ✅
2. This PLAN reviewed and agreed within the team.
3. PRD 1 written → built → milestone observed → committed.
4. Repeat through PRD 7, no skipping.
5. Warm-up games against friendly teams (uncounted) to shake out protocol mismatches.
6. Counted games against at least two different teams.
7. Submission gate (`spec-guard` Mode 4), tag `v1.0-submission`, Moodle submission per member.
