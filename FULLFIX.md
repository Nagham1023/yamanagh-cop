# Full-fix pass — five foundational corrections before PRD 6

Status: **Doc only. `todoFullFix.md` is the execution checklist; nothing below is built yet.**

## Why this exists

A cross-cutting critique pass — five specific notes, checked directly against `police_thief_p2p.pdf` rather than against this repo's own prior paraphrases of it — found that five load-bearing pieces of this project's foundation were built on misreadings of the book: the scent-map wire architecture, the negotiated config's schema, the private config's file format, the PRD 6 scent-model negotiation ceremony, and the belief-map's update math. None of these are PRD 6 work; all of them are corrections to PRD 1, 2, 4, and 5 territory that PRD 6 would otherwise be built on top of. This doc is the rationale; `todoFullFix.md` is the 150+-item execution checklist. Same PRD → TODO → execute discipline this repo already uses for every layer and revision — this is a cross-cutting layer, not a single PRD, so it gets its own doc rather than slotting into one `PRD-N-*.md`.

Every claim below was verified by reading the book directly (`uv run --with pypdf python3`), not by trusting this repo's own `PLAN.md`/PRD paraphrases — the same lesson this project already learned once, at the PRD 2 → PRD 4 rule-27 carve-out.

## Finding 1 — the scent map is a Tool-call data channel, not natural language

**Book, ch. 6.5 (p.65-66):** "The strategy module directs the client to use a Tool against the FastMCP server in order to gather data, builds a rich prompt that includes the statistics and the scent maps, and sends it to the language model in order to compose a calculated deception text — or a psychological analysis of the opponent's language."

**Book, ch. 6.4 (p.63-65):** "Each side knows where it itself is, and receives the opponent's scent map (each side reads the other side's scent field, not its own) and a verbal hint that may be lying." Belief maps are built from that map plus hints, via Bayes.

**Book, ch. 4.4 (p.46, already used to ground PRD 4 Revision 2):** the worked example reads absolute per-cell numeric τ — (1,4)=0.81, (5,2)=0.00 — across near and far cells alike. Not a compass-direction sentence.

**What this means:** rules 26/27 ("free natural language only," "no direct numeric position protocol") govern the *verbal hint* channel — the psychological, Intent-flagged, lie-capable layer. They do not govern a scent-map data channel, because a scent field isn't a position claim about the opponent — it's shared, cryptographically-locked, formula-derived environmental residue (ch. 4.5 treats it that way explicitly, see Finding 4). The book's architecture is two distinct channels: a Tool call returning the opponent's scent map as structured numeric data, and a separate natural-language hint that may lie.

**What was built instead:** PRD 4 Revision 1 (`generate_scent_report`/`dominant_scent_direction` in `src/cop/reasoning/hint.py`) collapsed the opponent's scent field into a two-word compass sentence (`"Scent strongest to the north east."`) and rode it inside `receive_hint`'s second string parameter, alongside the verbal hint. Revision 2 (just committed, `087b421`) fixed a real bug in that mechanism's direction math but didn't question the mechanism's shape. `WIRE-CONTRACT.md` (written last session, uncommitted) already self-flagged `scent_report` as "this repo's own invention, not book-mandated" — this finding confirms that flag was correct and completes the fix it was gesturing at, rather than opening a new question.

**This also dissolves Finding 3 from the prior critique pass entirely.** That pass asked whether the scent channel needed distance-gating to match the book's implied "silence when far" pacing. It doesn't — because the premise (a self-report broadcast) is wrong. The book hands over the full opponent scent map via Tool call; there's no pacing deviation to document once the channel is the right shape.

**Fix direction — PRD 4 "Revision 3":** a dedicated MCP tool (name TBD in `todoFullFix.md` §C) that returns the sender's own `ScentField.sample()` output directly — already exactly the right `dict[Position, float]` shape (see codebase audit below) — as structured numeric data. `receive_hint` reverts to a single `text: str` parameter. `update_from_scent_report` in `memory/belief.py` is reworked to consume real per-cell values instead of a re-quantized `Position` recovered by running the old sentence back through `interpret_hint`. Given rule 27 is **[FATAL]**, and this project has precedent for raising exactly this kind of question explicitly rather than deciding it alone (Revision 1's own "resolving the rule 26/27 tension" note), the new tool's shape gets an explicit `rule-auditor` sign-off before it's treated as settled — not just a verification pass after the fact.

### Rule 27 legal review (§C7, built)

Built shape: `share_scent_map() -> dict` (`src/cop/tools/mcp_server.py`) — zero parameters, returns `{"cells": [[col, row, value], ...]}`, the sender's complete `ScentField.full_field()`, wire-serialized (`tools/scent_wire.py`). `receive_hint(text: str) -> dict` is unchanged in kind, narrowed to drop `scent_report`.

Rule 27, verbatim intent (RULES.md): **[FATAL]** — no direct numeric position protocol; the peer must never learn the opponent's coordinates as data, only as language that may lie. Walking through why `share_scent_map`'s payload isn't that:

1. **A τ value at a cell is not a claim "the opponent is at this cell."** It's the sender's own cumulative emission history — every cell the sender has been near recently carries a nonzero value, most of them cells the sender *isn't* currently standing on. Ch. 4.4's own worked example treats a distant `τ=0.00` reading as real, useful data precisely *because* it isn't a position claim — it's an absence-of-residue signal, structurally different from "I am at (x, y)."
2. **The book's own architecture puts this data outside the hint's rule 26/27 boundary.** Ch. 6.4/6.5, read directly (Finding 1 above): "the client uses a Tool... to gather data... receives the opponent's scent map" is presented as the *mechanism*, separate from "a verbal hint that may be lying." Rule 26/27 is stated in the context of the communication/deception layer (Table 21, the `[trash_talk]`/hint machinery) — the scent field belongs to a different subsystem (Table 16, pheromones) with its own rule (23, cryptographic locking of the *formula*, not a ban on exchanging its output).
3. **Precedent for "how much of the game state can legally be data, not language":** rule 27's own text ("no direct numeric *position* protocol") is scoped to position, not to every number in the game. `BarrierSet`'s eventual declaration channel (PRD 6, rules 15/16) will also carry structured, non-position numeric data (cell coordinates of barriers) — the project's own rules distinguish "your opponent's position" (forbidden as data) from other structured game facts (permitted, sometimes required, as data).
4. **What would make this a rule 27 violation, for contrast:** if `share_scent_map` returned or could be trivially inverted to yield the sender's own current position with high confidence and low noise. It can't: the field is history, not a live GPS ping — a sender standing still for many turns does concentrate mass near itself (matching the book's own "ants' stigmergy" framing, not a bug), but that's an *inference* the receiver's belief map has to do the same work ch. 6.4 describes (Bayesian update, argmax), not a number the sender directly asserted as "my position."

Submitted to `rule-auditor` for explicit sign-off before C8's test rebuild began. **Not a clean pass on the first submission** — worth recording honestly rather than only the resolution.

**What `rule-auditor` found:** `ScentField`'s emission kernel deposits its single highest weight (0.90) fresh and undecayed on the sender's *current* cell every `advance()` call, while every other cell in the field is decayed first. `share_scent_map()` sends the entire field, unwindowed. Consequence: a receiver needs no Bayesian inference at all — plain `argmax` over the payload lands on, or within one cell of, the sender's actual current position on essentially every turn. The auditor's framing: that's functionally a position ping even though no single field is literally labeled "my position," and rule 27 is **[FATAL]**. It also flagged, honestly, that its own re-read of ch. 6.5's Hebrew text was low-confidence, and floated a real alternative: "the client uses a Tool against the FastMCP server to gather data" could describe a peer querying its *own* local data to build its *own* LLM prompt, not a cross-peer wire transfer — a different mechanism than the one this section built around.

**Raised directly to the project owner rather than resolved unilaterally, given the fatal-rule stakes** — same discipline as Revision 1's own "resolving the rule 26/27 tension" note; their answer:

> Keep the full-board Tool design as built. The "freshest deposit reveals current position" property isn't something this redesign introduced — it's intrinsic to Table 16's own emission formula (0.9 at the emitting cell, every turn, book-specified, not invented here). Implementing ch. 4.4's corroboration mechanic *at all* carries this property; Revision 1/2's natural-language `scent_report` leaked comparably precise information already (a concentrated-quadrant sentence, updated every turn, effectively the same signal in lower resolution) without anyone treating that as a rule 27 problem. Proceed to §C8.

**Resolution:** ship `share_scent_map()` as built, full-board, no additional windowing/staleness mitigation. This is a judgment call about the book's own design, not a settled textual certainty — recorded here so it's visible to a future reader (or the thief-repo teammate, via `WIRE-CONTRACT.md`) rather than silently assumed safe.

**Follow-up, upgraded from judgment call to textually confirmed**: a later session raised a direct challenge to this — a claim, from outside this repo, that the opponent should only ever receive a windowed **5×5** scent grid (i.e. `pheromone_grid_size` itself as a transmission cap), not the full field. Re-reading ch. 4.3/4.4 a second time, specifically against that question, settles it: ch. 4.3's own definition of `pheromone_grid_size` ("a scent field of size [scent field size] — e.g. 5×5 — is created **around its position**... the cell where the agent resides is the emission centre") is unambiguously describing the **single-deposit kernel** (Fig. 4's radial falloff, one `advance()` call), not a cap on what a peer may later read back. Ch. 4.4 then describes reading that accumulated history as "each agent can sample **the board**," and its own worked example reads an explicitly distant, empty cell (τ=0.00) as meaningful negative evidence — which only makes sense over a board-wide accumulated trail, not a fixed local window that couldn't reach that cell in the first place. The two "5×5" ideas — the emission kernel and a hypothetical transmission window — are easy to conflate from a paraphrase, but the book only defines the first one. `PARAMETERS.md`'s Table 16 entry now states this explicitly to head off the same misreading recurring.

## Finding 2 — Appendix B's config schema is nested, and its field names are the binding ones

**Book, Appendix B (p.126-132), the actual `config/game.json` shape:**

```json
{
  "schema_version": "1.2",
  "agreed_between": ["group-a", "group-b"],
  "board_and_agents": {
    "grid_size": 7, "num_agents": 2,
    "thief_start": [3, 3], "cop_start": [0, 0],
    "axis_origin_corner": "top-left", "axis_start_index": 0
  },
  "world": {"map_area": "New York", "hint_max_words": 15},
  "movement_and_barriers": {
    "move_set": ["N", "S", "E", "W", "STAY"],
    "max_barriers": 14, "max_moves": 35, "survival_threshold": 35
  },
  "scoring": {
    "capture_cop": 20, "capture_thief": 5,
    "survival_cop": 5, "survival_thief": 10,
    "tie_score": 2, "technical_loss": 0
  },
  "pheromones": {
    "pheromone_center_intensity": 0.9, "pheromone_decay": 0.10, "pheromone_grid_size": 5
  },
  "network_and_league": {
    "response_timeout_sec": 30, "watchdog_timeout_sec": 60,
    "num_games": 1, "diversity_reward": 10, "min_games_to_pass": 2,
    "max_games_per_team": 10, "token_budget_per_series": 200000
  },
  "rate_limiter_gatekeeper": {
    "requests_per_minute": 30, "concurrent_requests": 2,
    "retry_backoff_sec": 5, "max_retries": 3, "queue_depth": 100
  }
}
```

**p.132, verbatim:** the shared JSON's values overlay every key the private TOML also holds — so the private file can never weaken a signed term — and "the full mandatory dictionary for every parameter — name, meaning, value — is concentrated in the table of mandatory parameters in the appendix." That table (Appendix ו / the book's final appendix, p.151-155) uses these exact nested leaf names.

**What was built instead:** `.claude/skills/spec-guard/references/PARAMETERS.md` and `config/shared/config_dev_g01.json` use flat, invented names (`board_size`, `barrier_quota`, `scent_source_strength`, ...) that were never transcribed from Appendix B — they were paraphrased, the same failure mode already caught once for rule 27. `check_config.py`'s alias-matching (`lookup()` matches by last path segment against a registered alias list) has been quietly absorbing part of the mismatch without anyone noticing the base names were wrong.

**Table 20 (p.157)** also gives the canonical file-naming convention: `declaration_<game_id>.json`, `config_<game_id>_g<NN>.json`, `log_<game_id>_g<NN>.json`, `result_<game_id>.json`. The config/log names already match what `CLAUDE.md`'s own commands use today — no change needed there. `declaration_`/`result_` files don't exist yet (later-PRD territory), but the correct name should be on record now so nothing invents a different one later.

**Fix direction:** Appendix B's nested names become the file, `PARAMETERS.md`, and `check_config.py`'s source of truth. Codebase audit (below) found the blast radius is much narrower than the schema change might suggest: `GameConfig.from_dict()` (`src/cop/shared/config.py`) is the *only* place in `src/` doing flat-key JSON lookups — every other file reads `config.<attr>` via dataclass attribute access, name-agnostic to the JSON's shape. **Decision, flagged and confirmed during planning:** `GameConfig`'s internal Python attribute names stay as they are — Appendix B governs the *file* schema (what's negotiated, signed, hashed), not either team's internal variable naming, and renaming internals would touch ~40 files for zero compliance benefit. `from_dict()` becomes a one-function translation layer between the nested file and the existing internal dataclass shape.

## Finding 3 — the private config is `config/game.toml`, in TOML, and `opponent_url` lives in `[network]`

**Book, p.130-132, verbatim:** `config/game.toml` — sections `[game]` (group_name, group_id, sub_game_number, members, repos), `[network]` (`my_port`, `opponent_url` — "the only thing I know about the opponent" — `turn_timeout_seconds`), `[strategy]` (thief_class/police_class, optional), `[trash_talk]` (provider, optional), `[llm]` (model, step_deadline_seconds), `[email]` (recipient, mode).

**What was built instead:** `src/cop/shared/private_config.py` loads **JSON**, not TOML, and implements exactly one of the six sections (`[trash_talk]`, unwrapped — `config/private/trash_talk_dev.json`). `opponent_url` isn't a config field anywhere in this repo (zero grep hits) — the peer's URL is a plain runtime string manually threaded through `take_turn(peer_url)`/`send_to_peer(peer_url, ...)` at every call site, and `PRD-5-cloud-exposure.md` explicitly frames this as deliberate scope ("a human, operational step, not something this layer's code automates"). The book settles that question differently: `opponent_url` has a real, specified home.

**Fix direction:** `config/game.toml`, all six sections, loaded via stdlib `tomllib` (already available, `requires-python = ">=3.11"`, zero new dependency). `Orchestrator`/`take_turn` default `peer_url` from the loaded private config's `[network].opponent_url` when not explicitly overridden — keeping the explicit-parameter path for tests, since a live CLI entry point (`uv run python -m cop peer`, referenced in `CLAUDE.md`'s own Commands section) doesn't exist in this repo yet and isn't in scope here. `PRD-5-cloud-exposure.md`'s framing gets corrected to point at the new field instead of "a human, operational step."

## Finding 4 — ch. 4.5 mandates a scent-model negotiation + crypto-lock ceremony, and explicitly recommends sharing code

**Book, ch. 4.5, p.47, verbatim:** "Before the series opens between the two groups, they must exchange the emission model and the decay model — in full, including a concrete numeric example... so that both sides interpret exactly the same formula in exactly the same way, and only then lock the agreement cryptographically — e.g. a hash (SHA-256) of the agreed formula together with the numeric example... It is even recommended, and even permitted, that one group supply the other with the shared scent-mechanism code itself, so that both sides run exactly the same behavior."

**Fix direction:** `WIRE-CONTRACT.md` (written last session, not yet committed) gets extended with this ceremony explicitly — a concrete numeric worked example (e.g. "a cell at the centre receives τ=0.9; after one round of decay at ρ=0.10 it receives 0.9·0.9=0.81") that both teams hash together before the series, and an explicit recommendation to offer the teammate the `ScentField` implementation itself rather than only a written schema. This section is downstream of Finding 1's redesign (the ceremony should describe the mechanism as it actually ships, i.e. Tool-based, not the old language-based one).

*Secondary, related finding, not one of the five but found in the same page range and directly relevant to work already sitting uncommitted*: p.51's `Hcommit` code example commits only `state‖move‖intent‖nonce`, but the surrounding prose notes the reference implementation's actual payload is richer — it also folds in the hint text, an intent classification, step number, and role. `PRD-6-prep-commit-payload-spec.md` (built last session, uncommitted) currently scopes "State" to `own_pos`/`steps_taken`/`barriers_placed` only, following the minimal 4-field example. Real, but PRD 6 hasn't started building the actual payload yet — flagged here and left as a note for that PRD's own doc, not one of `todoFullFix.md`'s items.

## Finding 5 — two smaller corrections

**Belief map (ch. 6.4, p.63-65; Figure 8, p.64):** the book's own mechanism is a genuine Bayesian update with an explicit "reliability coefficient" (מקדם אמינות) applied to incoming text specifically because it may be lying — not a flat multiplicative reweight. Figure 8's caption confirms barrier cells are drawn with zero belief on the heatmap. Neither a prediction/diffusion step nor a negative-evidence mechanism appears anywhere in the book's own model — this repo's existing enhancements in that direction (if any get proposed later) are legitimate design contributions, not compliance gaps, and should be documented as such rather than treated as bugs.

**What was built instead** (codebase audit, below): `memory/belief.py`'s `update_from_hint`/`update_from_scent_report` are hardcoded multiplicative boosts (`_HINT_BOOST = 3.0`, `_SCENT_REPORT_BOOST = 6.0`) applied to a focal cell plus its four orthogonal neighbours, then renormalized — the module's own docstring already admits this is "a simpler weighted-reweighting scheme than a full Bayesian posterior." No named, data-driven reliability coefficient exists — the boost-constant gap is the only proxy for truthfulness. `BeliefMap` has zero barrier awareness: no `Barriers` field, no import, and `most_likely_cell()` is an unfiltered argmax that **can currently return a barrier cell**, propagating straight into `self.game_state.target_pos` — the cop's actual targeting logic.

**Fix direction:** a genuine Bayesian update with an explicit, named reliability coefficient (config-driven, not a hardcoded literal) on hint evidence; `BeliefMap` gains barrier awareness (a `Barriers`/`BarrierSet` reference); `most_likely_cell()` excludes barrier cells from the argmax; the standing "no cell ever hits exactly 0" design invariant gets a documented, barrier-specific carve-out rather than a silent contradiction.

**Built (§E).** `update_from_hint` is now a real two-branch posterior update: `P(state|evidence) ∝ P(evidence|state)·P(state)`, where the hint's focal region (its cell + orthogonal neighbours) gets likelihood `_HINT_RELIABILITY` (split evenly across the region's cells, not applied per-cell independently — an early implementation bug caught by the corroboration milestone tests failing, fixed before this shipped) and every other tracked cell gets `(1-_HINT_RELIABILITY)/N` — a real down-weight, not "left unchanged" the way the old flat boost left non-focal cells alone. `_HINT_RELIABILITY = 0.6`, `_SCENT_MAP_BOOST_SCALE = 20.0` (retuned up from the interim §C6 value of 6.0 — the new hint math's region-concentration effect gives a lying hint a much stronger head start than the old flat boost did, so the scent map's own counter-evidence needed proportionally more weight to still win the corroboration milestone; solved algebraically, not by guessing, then verified against every existing test). **Reliability-coefficient status, decided explicitly:** a local, code-level constant — not a new Appendix B config field. The book gives the *concept* (ch. 6.4's own "מקדם אמינות") without a specific number, and this value is each team's own algorithm choice, not a negotiated game rule — same category as `movement.DELTAS` or `CopBrain`'s tie-break order, not something `check_config.py`/`PARAMETERS.md`'s mandatory-parameter table governs. `BeliefMap` gained real barrier awareness: `uniform(board, barriers=...)` seeds barrier cells at exactly 0 from construction, `zero_out_barriers(barriers)` re-syncs live as new barriers get placed (wired into `Orchestrator.take_turn()`, not just built and left unused), and `most_likely_cell()` filters barrier cells defensively via a remembered `_barrier_positions` set — a second, independent enforcement layer on top of the values already being 0, matching this project's "never trust a single enforcement layer" discipline. Sanity-check sabotage confirmed both the reliability coefficient and the barrier filter are load-bearing (reverting either broke exactly the test built to catch it, nothing else). No book-mandated feature was left unbuilt after this pass — no "enhancement beyond the book" framing was needed for the note in `PRD-4-language-and-scent.md`, since everything built here traces directly to ch. 6.4/Figure 8.

**Rule 25's negotiated exception (ch. 6.5, p.65-66), verbatim:** "as part of the negotiable rule system, both sides may agree in advance — in the negotiation stage before the game — to allow an LLM-based tactic to also influence the move decision, instead of exclusive reliance on the algorithm... not valid unless explicitly and mutually agreed, documented between the groups... the local algorithm must still enforce move legality and reject any illegal move the model proposes." Documentation-only addition to `PLAN.md`/a PRD doc — `CopBrain` is already algorithmic-only by default and nothing currently proposes exercising this exception, so no code changes.

## Codebase audit summary (full detail in the approved plan file)

Three parallel research passes confirmed the blast radius before any item was written into `todoFullFix.md`:

- **Config schema** — narrower than feared: `GameConfig.from_dict()` is the only flat-key consumer in `src/`; everything else is dataclass-attribute access, name-agnostic. `check_config.py` already does arbitrary-depth flattening + alias matching, needs no structural change, only alias-table additions.
- **Private config** — larger than expected: only one of six required TOML sections exists at all, in the wrong format (JSON), and `opponent_url` doesn't exist as a config concept anywhere.
- **Scent/hint wire** — the largest single item, but with a clean seam: `ScentField.sample()` already returns exactly the numeric structure the redesign needs; it's just being thrown away by collapsing it into two words before it reaches the wire.
- **Belief map** — confirmed gap on both counts (no reliability coefficient, no barrier awareness), with a live, unresolved risk already in production: a barrier cell can currently win `most_likely_cell()`.

## Rules touched

| Rule | How this pass affects it |
|---|---|
| 11, 12 | Config schema migration — byte-identical, mandatory-minimum enforcement now checked against the *correct* field names, not invented ones. |
| 23 | Ch. 4.5's negotiation + crypto-lock ceremony (Finding 4) — extends `WIRE-CONTRACT.md`, still ahead of PRD 6's actual lock. |
| 26, 27 **[FATAL on 27]** | Scent-map redesign (Finding 1) — moving numeric scent data off the natural-language channel and onto a dedicated Tool, with explicit `rule-auditor` sign-off on the new tool's shape before it's treated as settled. |
| I6, I9 | Reinforced throughout — reliability coefficient and barrier-awareness config-driven, not hardcoded; every wire-facing change re-verified as untrusted-input-safe. |

## Out of scope for this pass

- PRD 6's own Commit-Reveal build (state machine, nonce, four-phase exchange) — untouched; this pass only corrects the foundation PRD 6 will sit on.
- The commit-payload richness gap (Finding 4's secondary note) — deferred to PRD 6's own doc.
- Rule 25's exception itself being exercised — documented as available, not adopted.
- A live CLI entry point (`uv run python -m cop peer`) — `opponent_url`'s new home doesn't require building one; that's separate, later-PRD scope.

## Builds on

PRD 1 (`domain/`, config), PRD 2 (`Orchestrator`/wire infra), PRD 4 (language/scent — this pass supersedes Revision 1/2's scent-report shape with "Revision 3"), PRD 5 (private config, opponent URL framing). Precedes PRD 6 — this is explicitly a prerequisite pass, not a parallel track.

See `todoFullFix.md` for the granular, 150+-item execution checklist.
