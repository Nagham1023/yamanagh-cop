---
name: spec-guard
description: Audit code, config, PRDs or plans for the Haifa "Distributed Cops-and-Robbers over P2P" final project against the 55 binding rules (Appendix E) and the mandatory parameter table (Appendix F). Use before writing or reviewing any project code, when creating or editing a game config, when drafting a PRD, and as the gate before any commit, game or submission tag.
---

# spec-guard

The failure mode in this project is not bad code. It is code that runs beautifully and violates a rule that carries a **zero**. Sixteen of the fifty-five rules are fatal, and most of them are invisible at runtime — a weak nonce, a GUI that renders one cell too many, a config that differs by a newline. Nothing in the game will tell you. The audit at the end will.

This skill exists so that never happens.

## Sources of truth, in order

1. **Appendix F (`references/PARAMETERS.md`)** — the only source of truth for every numeric value. Nothing in the book body, in a figure, in a code sample, or in the reference repo overrides it.
2. **Appendix E (`references/RULES.md`)** — the 55 binding rules with their sanctions.
3. The book body — illustrative unless a passage explicitly says it is binding.
4. The reference repo `Game-P2P-Cop-Chase` — teaching material only. Where it deviates from the book, **the book wins**.

If the book contradicts itself, you may choose either reading — but the contradiction, the choice and the reasoning **must be written into the report**. A documented, reasoned choice is never held against you.

## When to run which mode

| Situation | Mode |
|---|---|
| Just generated or edited project code | **Mode 1 — code audit** |
| Created or changed a game config | **Mode 2 — config validation** |
| About to play a real (counted) game | **Mode 3 — pre-game gate** |
| About to tag `v1.0-submission` | **Mode 4 — submission gate** |
| Drafting a PRD | **Mode 5 — PRD check** |

---

## Mode 1 — Code audit

Read `references/RULES.md`. Then check the code against the patterns below. These are the specific ways the fatal rules get broken in practice — every one of them looks fine while the game runs.

### Cryptography

| Look for | Why it is fatal |
|---|---|
| `random.` anywhere near nonce generation | Rule 18. Must be `secrets.token_hex` / `secrets.token_bytes`. `random` is seeded and predictable — the protection is nil. |
| `==` comparing two hashes | Rule 19. Use `secrets.compare_digest`. |
| `json.dumps(...)` in the commit payload without `sort_keys=True, separators=(",", ":")` | Rules 11, 19. Two peers must hash byte-identical input, or every honest game fails its own audit. |
| A nonce sent in the same message as the move | Rule 18. The nonce is released **only** in the final reveal, at game end. |
| Commit payload missing `state`, `move`, `intent` or `nonce` | Rule 17. `State` binds the commit to this turn; `Intent` forces you to pre-declare truth-or-lie. |
| No hard failure path on hash mismatch | Rule 19. Mismatch must produce a technical loss, not a warning. |
| Scent constants not included in the pre-game locked declaration | Rule 23. |

### Decentralization

| Look for | Why it is fatal |
|---|---|
| Any module holding live game state imported by both the cop and the thief | Rules 1, 2. Shared constants are fine; shared **state** is disqualification. |
| Cop and thief started from a single process, thread, or asyncio task group | Rule 1. Two OS processes, separate config directories. |
| A test harness that instantiates both brains in one interpreter | Rules 1, 2. Acceptable for stage-1 unit tests of pure board logic; never for a game. |
| Anything in the live GUI drawn from the true board rather than the belief map | Rules 8, 9. The GUI may draw: your own position, barriers you know about, your scent readings, your belief heatmap. It may **not** draw the opponent's actual position. |
| No orchestrator as single entry point; no state machine; no deadline tracker; no watchdog | Rules 3–7. |

### Protocol and language

| Look for | Why it is fatal |
|---|---|
| Coordinates, row/col numbers, or a structured position payload in the hint field | Rule 27. In-game communication is **free natural language only**. Numeric coordinates over the wire are legal only in stage 2 of development, on localhost, before the language layer exists. |
| A hint longer than the word limit | Table 14. The limit applies to template mode and must be stated in the LLM's system prompt. |
| The LLM's output being parsed into a move | Rule 25 (recommendation) and the book's hard framing: the move is **always** decided in Python. The model touches only the verbal layer. |
| A diagonal in the move set | Rules 13, 14. |
| Barrier placement not announced, or announced with a different cell than the one used | Rules 15, 16. |
| Barrier placed further than one cell from the cop, or without forgoing the move | Ch. 3 barrier law. |
| No capture on a barrier dropped on the thief's cell, or no capture when the thief has zero legal moves | Rules 46, 47. |
| Barrier Capture Claim gated on matching the cop's *believed* target instead of firing unconditionally on the barrier's own cell | Rule 46, 21. The cop has no ground truth (rules 1/2) — gating the claim on belief silently misses a real capture whenever belief is off by even one cell. Confirmed as a real regression in this repo (`8cc9082`), not a hypothetical. |

### Cross-peer termination

| Look for | Why it is fatal |
|---|---|
| The game loop not stopping when the peer's Final Reveal arrives (Ch. 5.3.2 Step 4 — the book's own diagram literally labels it "end of game") | Rule 35. Looping past it risks computing a locally different outcome than the peer already settled on — a contradictory report zeroes both teams. Confirmed as a real regression in this repo (`8cc9082`), not a hypothetical. |

### Secrets and reporting

| Look for | Why it is fatal |
|---|---|
| `credentials.json` or `token.json` not in `.gitignore` | Rules 39, 40. A leaked secret is permanent — it survives in git history after deletion. |
| Gmail scope wider than send-only | Rule 30. |
| No token-bucket rate limiter on outgoing mail; no DOS detector | Rules 28, 29. |
| Final report sent as body text rather than an attached JSON file | Rule 34. |
| Report missing the commit hash or the token totals | Rules 53, 54. |

### Report the audit like this

```
spec-guard code audit — <what was audited>

VIOLATIONS (fatal)
  rule 18 — nonce generated with random.randint in crypto/commit.py:42
            → must be secrets.token_hex(16)

VIOLATIONS (non-fatal)
  rule 6  — no deadline tracker around the await on the opponent's tool call

NOT YET APPLICABLE
  rules 28-30, 32-35 — reporting layer, arrives in PRD 7

CLEAN
  rules 1, 2, 13, 14, 17, 19
```

Never report a rule as clean unless you actually looked at the code that implements it. "Not yet applicable" is the honest answer for layers that don't exist yet.

---

## Mode 2 — Config validation

```bash
python scripts/check_config.py config/game.json
python scripts/check_config.py config/game.json --json
```

Then, once both teams have exchanged their file:

```bash
python scripts/check_config.py --identical cop/config/game.json thief/config/game.json
```

The identity check is rule 11 and it is fatal. Note that a config which parses to an equal object can still fail — differing whitespace, key order, or CRLF line endings all break byte-identity. Serialise both sides with `sort_keys=True, separators=(",", ":")`.

The script checks **numbers only**. It cannot see the 55 behavioural rules; run Mode 1 as well.

Also confirm by hand, since the script cannot:

- The config file is named per game (`config_<game_id>_g<NN>.json`) so any game is reconstructable — mandatory rule 3.
- The config file is committed to the repo — mandatory rule 4.
- The parameters are cryptographically locked before the first move — mandatory rule 1 and rule 23.
- Any value raised above its minimum was **agreed with the opponent**, not raised unilaterally.

---

## Mode 3 — Pre-game gate

Run before every counted game. All must be true:

- [ ] Config validated and byte-identical with the opponent (Mode 2).
- [ ] Step-0 declaration signed and sent, containing hardware spec, LLM name, token budget, team code, sub-game number, **and the exact GitHub commit hash being played** (rules 24, 53).
- [ ] Scent model constants locked in that declaration (rule 23).
- [ ] Number of games played so far declared honestly (rules 37, 38).
- [ ] Tunnel up and reachable from outside your network (rule 10).
- [ ] Both processes running independently, separate config dirs (rules 1, 2).
- [ ] This opponent has not already been played for a counted game (rule 52).
- [ ] Games played remains within the cap of 10 (Table 18).

After the game:

- [ ] Full mutual log audit performed (rule 36).
- [ ] Result agreed with the opponent, and **both** teams send their own separate JSON report — a missing or contradictory report zeroes **both** teams (rule 35).
- [ ] Report attached as JSON, sent to the agent reporting address, including token totals (rules 33, 34, 51, 54).

---

## Mode 4 — Submission gate

- [ ] Two separate GitHub repos, cop and thief, accessible to the lecturer, cross-linked in both READMEs (rule 49).
- [ ] Each repo contains at minimum: `README`, `config/`, **PRD files**, a **PLAN** file, **TODO** files (rule 50).
- [ ] Git tag `v1.0-submission` created and pushed (rule 41).
- [ ] Academic report complete in `README.md`: model description, dilemmas faced, strategy, screenshots, and any RL curves (rule 42).
- [ ] Screenshots attached: the **belief map** in the GUI, and the **Replay app showing `Verified OK`** (rule 20).
- [ ] At least two counted games against two **different** teams (rules 31, 52).
- [ ] Both sides sent their end-of-game emails for every counted game (rule 35).
- [ ] `.gitignore` present and verified; **no secrets anywhere in git history**, not just in the working tree (rules 39, 40).
- [ ] Moodle form downloaded, filled, saved as PDF with no fields moved (rule 43).
- [ ] Submitted on Moodle **separately by each team member** (rule 44).
- [ ] Eight-character team code, no spaces, used consistently (rule 45).
- [ ] Self-score covers **code quality only**, never the league result (rule 55).
- [ ] Any book contradiction you relied on is documented with your choice and reasoning.

Verify the git-history point properly, not by looking at the file tree:

```bash
git log --all --full-history -- '*credentials*' '*token.json*' '*.env'
```

Any output means the secret is exposed permanently and the credential must be revoked and regenerated.

---

## Mode 5 — PRD check

A PRD for this project is only sound if:

- Every numeric value in it comes from `references/PARAMETERS.md`, referenced by name, never hard-coded from memory or copied out of the book body.
- Its milestone is stated as **observed end-to-end behaviour**, not "the code is written". "Two agents move legally on the grid and a barrier beyond quota is rejected" is a milestone. "Implement the board class" is not.
- It names which of the 55 rules the layer is responsible for satisfying, so the code audit has a target.
- It builds strictly on the layer below it. Skipping ahead means a bug in an upper layer hides behind instability in a lower one, and a single-variable investigation becomes an unsolvable multi-variable one.

The seven layers, in the only order the book permits:

| PRD | Layer | Rules that arrive here |
|---|---|---|
| 1 | Base logic: grid, movement, barriers, capture — single process | 13, 14, 46, 47, 48 |
| 2 | FastMCP over localhost, geometric messages | 1, 2, 3, 4, 5 |
| 3 | Blind strategy with full information | 25 |
| 4 | Natural language, scent, decay, belief map, deception | 23, 26, 27, and Table 14/16 |
| 5 | Cloud exposure and tunneling | 10, 6, 7 |
| 6 | Commit-Reveal, nonce, Step-0 | 17, 18, 19, 21, 22, 24, 53 |
| 7 | Gmail, GUI, Replay app | 8, 9, 20, 28-35, 51, 54 |

---

## The fourteen things that carry a zero

Keep these in working memory. Everything else costs points; these cost the project.

1. Cop and thief sharing a process or any live state (1, 2)
2. Live GUI showing the objective board (8, 9)
3. Config not byte-identical, or a minimum lowered (11, 12)
4. Undeclared or misdeclared barrier (15, 16)
5. No SHA-256 commit-reveal (17)
6. Nonce leaked before game end, or generated weakly (18)
7. Any hash mismatch at audit (19)
8. No replay verifier app (20)
9. Lying about a capture, in either direction (21, 22)
10. Scent model not locked pre-game (23)
11. Numeric position protocol instead of natural language (27)
12. Gmail scope wider than send-only (30)
13. A secret in the repo or in git history (39)
14. Reports missing or contradictory between the two teams (34, 35)
