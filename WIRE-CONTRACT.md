# Wire Contract — MCP Tool Surface (cop ⇄ thief)

**Status: proposal, not yet agreed.** Send this file to the thief-repo teammate before attempting a real connection between the two repos. Nothing below is binding until both sides confirm it in writing — this document exists specifically because that confirmation has not happened yet, and every turn it doesn't happen is a turn a real match cannot run.

**Changelog, for anyone re-reading an earlier draft:** the scent data used to ride as a second string field (`scent_report`) inside `receive_hint`. It's now a separate tool, `share_scent_map`, returning structured numeric data instead of a natural-language sentence — a correction to how this repo read ch. 6.4/6.5, not a stylistic change. If you reviewed a version of this file before that correction, re-read `receive_hint`/`share_scent_map` below; `receive_hint`'s shape narrowed too.

## Why this exists

`config/shared/config_<game_id>_g<NN>.json` (this project's negotiated, byte-identical, rule-11-locked config) is *the contract* for game rules — board size, quotas, scoring — per the book's own ch. 3.2 ("A Discrete Space and a Shared Contract"): "since both agents read the exact same file, both compute the same functions over the same win-condition tests, preventing a 'what are the rules' dispute before the game has even begun... the contract is fixed before the exchange begins... a necessary condition is that the contract be mutually agreed by both sides."

That same discipline has never been applied to the **MCP tool surface itself** — the actual function name, parameter names, types, and return shape each side's FastMCP server exposes and calls. The book's own minimal example (ch. 2.3, `receive_move(signed_move, signature)`) is explicitly illustrative, not a fixed standard — every team is free to invent its own shape, and MCP calls are schema-checked: if the two sides don't agree byte-for-byte on tool name and parameter names, a call from one side's client to the other's server fails outright, before a single move happens. This is arguably a *harder* failure than a rules mismatch (which can still produce a running, disputed game) — a schema mismatch means no game runs at all.

**You cannot negotiate the tool surface over the tool surface.** This has to be settled out-of-band — a shared document, agreed before the first connection attempt — exactly like the shared config already is.

**Before any tool call can happen at all, each side needs the other's URL.** That's a separate, prior problem from the tool schema below — where to *send* a well-formed `receive_hint` call, not what it looks like. This repo's answer (`todoFullFix.md` §B, Appendix B p.130-132): `config/game.toml`'s `[network].opponent_url` — a private, hand-edited, never-negotiated, never-hashed field ("the only thing I know about the opponent," the book's own words). `Orchestrator.take_turn()` defaults to it when no explicit `peer_url` is passed. This is operational, not part of the schema negotiation itself — no need for the teammate to match this repo's exact config format, only to have *some* way of knowing where to point their own client.

## The cop side's current proposal

Built and tested (PRD 2 → PRD 5) against itself only — this repo has never connected to a real, independently-built peer. Treat every field below as open to negotiation, not as a fait accompli. **Changed materially since the last version of this document** (PRD 4 "Revision 3", `todoFullFix.md` §C) — this is a new proposal, not a formality, even for a teammate who already reviewed an earlier draft.

**Transport:** FastMCP over Streamable HTTP (matches the book's own ch. 2.3 example).

**Tool 1: `receive_hint`** — the natural-language, psychological, lie-capable channel (rules 25/26/27).

| Parameter | Type | Meaning |
|---|---|---|
| `text` | `str` | The tactical hint — free natural language (rule 26), may be a lie (Table 21's `Intent` flag governs this on the sender's side; the receiver has no way to know which from the wire alone). Hard-capped at `hint_word_limit` words on the sending side (Table 14 #2), but the tool itself does not reject an over-limit string — it flags it in the ack instead (see below). |

**Return (the ack):**

```json
{"accepted": true, "word_count": 4}
```

`accepted` is `false` if `text` exceeds `hint_word_limit`; `word_count` is `text`'s actual word count, always reported regardless of `accepted`.

**Not negotiated, not needed to be:** the actual sentence content and vocabulary. Rule 26 makes this free natural language by design — each side parses incoming text with its own logic, however it chooses. Only the wire-level *structure* above (tool name, parameter name/type, ack shape) needs mutual agreement.

**Tool 2: `share_scent_map`** — the structured numeric data channel (ch. 6.4/6.5), separate from the hint above.

No parameters. Returns the sender's own current, complete scent field:

```json
{"cells": [[col, row, value], [col, row, value], ...]}
```

Each triple is one cell this sender has ever deposited or decayed scent near — `col`/`row` ints, `value` the current τ float. A cell absent from the list has never been touched; the receiver treats that as τ=0.0, the same convention `ScentField.sample`/`full_field` use internally. Not word-limited (Table 14 #2 governs verbal hints, not this channel) and not subject to `Intent` — this data is honest-by-construction, since nothing on the sender's side ever applies the lie flag to it (though nothing cryptographically enforces that yet either; see `RULE-19-SCENT-AUDIT-AT-PRD-6`, closed at PRD 6).

**Why two tools, not one payload:** ch. 6.4/6.5, read directly, describe two structurally different things — "a verbal hint that may be lying" (the psychological layer rule 26/27 governs) and "receives the opponent's scent map" via "a Tool against the FastMCP server... to gather data" (a separate mechanism). Earlier revisions of this repo squeezed the second into a natural-language field riding inside the first (`scent_report`), specifically because the natural-language design predated re-reading ch. 6.4/6.5 directly — corrected here, not iterated on further.

## A judgment call worth flagging explicitly to the teammate, not just to a reader of this file

`share_scent_map`'s full, unwindowed field means a receiver's plain argmax over the payload lands on (or within one cell of) the sender's actual current position on essentially every turn — Table 16's own emission formula deposits its single highest value fresh, undecayed, on the emitting cell every turn. This repo's own `rule-auditor` flagged this as a real rule 27 (**[FATAL]**, no numeric position protocol) tension before this design was treated as settled; the resolution reached (documented in full in `FULLFIX.md`'s "Rule 27 legal review" section) is that this property is intrinsic to implementing ch. 4.4's corroboration mechanic *at all* — the prior natural-language `scent_report` leaked comparably precise information already, just at lower resolution — not something this redesign introduced. **Worth the teammate's own independent read of ch. 4.4/6.4/6.5 and their own judgment call here**, not an assumption that this repo's resolution is the only defensible one.

## Another negotiable item, unrelated to any of the tools above: rule 25's LLM-move exception

Not a wire-schema item — flagged here anyway because it's exactly the kind of thing `config/game.json`'s "must be mutually agreed" principle exists to cover, and it's easy to miss since it's not a tool or a config field. Ch. 6.5 (p.65-66), verbatim: "as part of the negotiable rule system, both sides may agree in advance — in the negotiation stage before the game — to allow an LLM-based tactic to also influence the move decision, instead of exclusive reliance on the algorithm... not valid unless explicitly and mutually agreed, documented between the groups; one side may not unilaterally adopt such tactic."

This repo does not currently exercise the exception — `CopBrain` stays algorithmic-only by default (`PLAN.md`'s PRD 3 section). If either side wants to invoke it later, it needs the same explicit, written agreement this whole document is modeling — not something to discover mid-series because one side's `_decide_move` quietly started consulting an LLM.

## PRD 6 will add more of this — agree on a process now, not per-tool

PRD 6's Commit-Reveal work adds at least four more wire-surface items with the identical negotiation gap (see `PLAN.md`'s PRD 6 section and `PRD-6-prep-commit-payload-spec.md`):

- **Barrier declaration** (rules 15/16, both **[FATAL]**) — no channel exists yet on either side, as far as this repo knows.
- **Capture claim / capture response** (rules 21/22, both **[FATAL]**).
- **The Commit-Reveal envelope itself** — commit, acknowledge, reveal, final-reveal.
- **The scent-model negotiation ceremony itself** (ch. 4.5) — exchanging and cryptographically locking the emission/decay formula together with a concrete numeric worked example, before either side's `share_scent_map` values can be trusted at audit time. See the dedicated section below.

Recommend agreeing on a *process* with the teammate now — e.g. "each side sends a diff of this file before implementing any new tool, and the other side confirms before either implementation starts" — rather than re-running this exact fire drill once per PRD 6 sub-feature.

## The ch. 4.5 scent-model negotiation ceremony

Ch. 4.5, verbatim (translated): "Before the series opens between the two groups, they must exchange the emission model and the decay model — in full, including a concrete numeric example... so that both sides interpret exactly the same formula in exactly the same way, and only then lock the agreement cryptographically — e.g. a hash (SHA-256) of the agreed formula together with the numeric example... It is even recommended, and even permitted, that one group supply the other with the shared scent-mechanism code itself, so that both sides run exactly the same behavior."

**Concrete numeric example to exchange and hash** (this repo's own values, Table 16): a cell at the emission centre receives τ=0.9; after one round of decay at ρ=0.10 it receives 0.9·(1−0.10)=0.81; the full radial kernel (Figure 4) is the 5×5 grid in `src/cop/memory/scent.py::_KERNEL_GRID`.

**Recommendation, per the book's own text above:** offer the teammate `src/cop/memory/scent.py` directly — the `ScentField.advance()` implementation — rather than only a written formula description. Two independently-written implementations of the same formula are exactly the kind of thing that drifts in a subtle rounding or ordering detail; shared code doesn't have that failure mode. This is explicitly book-endorsed, not a shortcut.

**This ceremony's own lock is PRD 6's job**, not built yet — this section documents what needs to happen, cross-referenced from `PRD-6-prep-commit-payload-spec.md`.

## Status log

- **Not yet sent to the teammate.** This file is the draft to send.
- **Not yet confirmed compatible against a real thief-repo peer.** Every automated test proving `receive_hint`/`share_scent_map` work has been this repo's own client talking to this repo's own server — PRD 5's own milestone explicitly can't reveal this gap, since it's the same code on both ends.
- **This revision changes the wire shape materially, not just its documentation** — `scent_report` is gone, replaced by a second tool with a different parameter/return shape entirely. If an earlier draft of this file was already shared with the teammate, this supersedes it and needs to go back as a new proposal, not an FYI.
