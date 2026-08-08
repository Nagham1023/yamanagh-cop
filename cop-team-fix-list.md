# Cop repo — confirmed gaps to fix (from the Thief side's review)

**Grounded against:** `police_thief_p2p.pdf` (book v3.0.0) directly, and your own `.claude/skills/spec-guard/references/RULES.md` (independently checked against the actual PDF, Appendix E pp.126-135 — it matches).

These are specific to your repo, not a comparison — nothing here depends on waiting for the Thief side or a joint reconciliation session. Feel free to hand this straight to your AI.

---

## 1. Rule 23 [FATAL] — scent-model cryptographic lock (ch. 4.5)

Your own `WIRE-CONTRACT.md` already states this is "still not built." Ch. 4.5, verbatim: *"Before the series opens between the two groups, they must exchange the emission model and the decay model — in full, including a concrete numeric example... and only then lock the agreement cryptographically — e.g. a hash (SHA-256) of the agreed formula together with the numeric example."*

Concrete: `Step0Declaration` (`integrity/step0.py`) currently signs hardware/code/config facts but has no field for a scent-formula-plus-numeric-example hash. Needs a dedicated hash of (emission formula + decay formula + one worked numeric example) computed and exchanged before move 1 — not folded silently into the general config hash, since the book calls this out as its own explicit ceremony.

## 2. Rule 11 — config-identity verification is a manual step, not a live exchange

`check_config.py --identical` is a human-run CLI hashing two files' raw bytes. This satisfies the *outcome* rule 11 requires (byte-for-byte identity) but relies on a human remembering to run it correctly before every match, not an automated pre-game gate. Worth considering whether `Orchestrator`'s own match-start sequence should call this verification itself (or something equivalent) rather than trusting it happened out-of-band.

## 3. Rule 49 — no channel for the opponent's repo URLs

`orchestrator_end_of_game.py`'s own docstring already flags this: `opponent_cop_repo_url`/`opponent_thief_repo_url` are accepted as external parameters because "this repo has no channel anywhere for learning the opponent's own repo URLs." Rule 49 requires "four links in both teams' JSON" (both repos, both directions) in the final report — currently that data has to be hand-supplied by whoever calls `report_game()`, which is fragile (easy to pass the wrong value or forget it entirely on a real run).

## 4. No live `negotiate`/Step-0 exchange tool

Not a rule violation by itself (rule 11 doesn't mandate a specific mechanism), but worth knowing: the Thief repo already built `negotiate()` (a live SHA-256-signed terms exchange, reusing the same Commit-Reveal primitive as per-turn sealing) and `receive_control` (live Step-0 exchange) as real MCP tools. If a live cryptographic negotiation ceremony ends up being the agreed approach for rule 11/rule 24, that's a reference shape already built and tested on the Thief side — not saying to copy it unilaterally, just flagging it exists if useful when this gets discussed.

---

Everything else checked (mutual audit — genuinely two-directional, capture-claim/response — actually built, Gmail scope, rate limiting, replay verifier) looked solid from a moderate-depth read of the current `main` branch (commit `f6397bf`).
