# The 55 Binding Rules — Appendix E

Source: *Distributed Cops-and-Robbers over a Peer-to-Peer Network*, Dr. Yoram Reuven Segal, book v3.0.0, Appendix E (מיפוי החוקים המחייבים).

Each rule has an **action class**:

- **MUST** (חובה) — mandatory.
- **MUST NOT** (איסור) — prohibited.
- **SHOULD** (המלצה) — recommendation, no mandatory sanction.

The sanction text is the book's own stated consequence. Where the sanction is disqualification or a zero score, the rule is marked **[FATAL]**.

---

## Group 1 — Network architecture, decentralization, local epistemology

| # | Class | Rule | Sanction |
|---|---|---|---|
| 1 | MUST | Run the cop code and the thief code in two **completely separate processes**. | **[FATAL]** Total failure and breach of the Zero-Trust model. |
| 2 | MUST NOT | Share memory or variables between the two sides under any circumstances. | **[FATAL]** Immediate disqualification of the solution for information leakage. |
| 3 | MUST | Define the orchestrator component as the **single entry point** to all subsystems. | Technical instability and loss. |
| 4 | MUST | Manage game states with a proper **state machine**. | Technical loss caused by system deadlock. |
| 5 | MUST | Reject any illegal state transition in the state machine. | Logic error leading to loss. |
| 6 | MUST | Implement a **deadline-tracking** mechanism to prevent freezing while waiting on the opponent. | System paralysis and loss on timeout. |
| 7 | MUST | Run a **watchdog** to monitor process crashes and perform controlled data extraction. | Game crash and loss of the official record. |
| 8 | MUST | Display **local truth only** in the live UI. | **[FATAL]** Disqualification of the system's legality for an information breach. |
| 9 | MUST NOT | Display the full objective board state in the live UI. | **[FATAL]** Project disqualification for illegal advantage. |
| 10 | MUST | Use a tunneling tool to expose the local server to the public internet. | Inability to compete in the league. |

## Group 2 — Spatial mechanics, physics, board constraints

| # | Class | Rule | Sanction |
|---|---|---|---|
| 11 | MUST | Verify the config file is **byte-for-byte identical** on both sides. | **[FATAL]** Game voided for broken symmetry. |
| 12 | MUST | Raise minimum values in the parameter table **only by mutual agreement**, and never lower them. | **[FATAL]** Falling below threshold disqualifies the score. |
| 13 | MUST | Move only in orthogonal directions. | Illegal move, technical loss. |
| 14 | MUST NOT | Make diagonal moves. | Move rejected by the opponent, loss. |
| 15 | MUST | Openly declare every barrier placement. | **[FATAL]** Board forgery, automatic loss at audit. |
| 16 | MUST NOT | Lie about the location of a barrier placement. | **[FATAL]** Severe grounds for disqualification. |

## Group 3 — Cryptography, log integrity, zero-knowledge

| # | Class | Rule | Sanction |
|---|---|---|---|
| 17 | MUST | Use a **Commit-Reveal protocol based on SHA-256**. | **[FATAL]** Absence of the mechanism renders the solution invalid. |
| 18 | MUST | Keep the **nonce absolutely secret until the game ends**. | **[FATAL]** Defence disqualified due to dictionary-attack exposure. |
| 19 | MUST | Technically forfeit the game on **any** hash mismatch at the audit stage. | **[FATAL]** Iron rule: score 0 to the forging team. |
| 20 | MUST | Build a **viewer application** that replays and verifies the game log. | **[FATAL]** Threshold condition for audit approval and for submission. |
| 21 | MUST | Declare only the truth when a thief is captured. | **[FATAL]** Immediate disqualification for denying reality. |
| 22 | MUST NOT | Falsely declare a capture. | **[FATAL]** Zero score and technical loss, no right of appeal. |
| 23 | MUST | Cryptographically lock the **scent-emission model** before the game starts. | **[FATAL]** Deviation in the decay formula voids the game. |
| 24 | MUST | Make a cryptographic **hardware declaration** before the game starts (Step-0). | Forfeits eligibility for the computational-fairness bonus. |

## Group 4 — Strategy, language, public network

| # | Class | Rule | Sanction |
|---|---|---|---|
| 25 | SHOULD | Do **not** delegate the movement decision itself to the language model; use it for text processing and behavioural profiling only. | No mandatory sanction, but blind reliance risks hallucinations, illegal moves and technical loss. |
| 26 | MUST | Conduct in-game communication in **free natural language only**. | Preserves the psychological character of the challenge. |
| 27 | MUST NOT | Use a direct numeric position protocol. | **[FATAL]** Disqualifies the game's character as defined in the rulebook. |
| 28 | MUST | Implement a **token-bucket rate limiter** for sending Gmail reports. | Prevents a 429 block that would paralyse team reporting. |
| 29 | MUST | Define a **DOS detector** giving hard protection to network resources. | Interface lock preventing the reporting account from being blocked. |
| 30 | MUST | Use **send-only scope** for the Gmail API. | **[FATAL]** Security breach leading to code disqualification. |

## Group 5 — League fairness, administrative procedure, competition integrity

| # | Class | Rule | Sanction |
|---|---|---|---|
| 31 | MUST | Play the minimum mandatory number of games against **different** teams. | **[FATAL]** Failing the minimum denies a passing grade. |
| 32 | MUST | Report game results automatically via the Gmail API. | Absence of a report disqualifies the points from that game. |
| 33 | MUST | Format the game report as a standard **JSON** data structure. | Code cannot process free text; the report is rejected. |
| 34 | MUST NOT | Send the final report as free text — only as an attached JSON file. | **[FATAL]** A non-JSON report is refused and leads to a zero. |
| 35 | MUST | Agree the result with the opponent, and have **each team send its own separate final report**. Non-reporting by one team, or contradictory reports, voids the game and gives 0 to **both**. | **[FATAL]** Primary enforcement mechanism against reporting fraud. |
| 36 | MUST | Perform a comprehensive **mutual log audit** at the end of every game. | Necessary precondition before agreeing the shared JSON result. |
| 37 | MUST | Accurately declare the number of games actually played, at the start of each game. | Threshold for computing the true competition factor. |
| 38 | MUST NOT | Falsely declare the number of games played. | **[FATAL]** Absolute disqualification for a discipline and integrity offence. |
| 39 | MUST NOT | **Ever** push secrets or credentials to the repo — even a private repo shared only with the lecturer. | **[FATAL]** Severe security failure and project failure. |
| 40 | MUST | Add credentials and secrets files to `.gitignore`. | Mandatory protection against Gmail API credential leakage. |
| 41 | MUST | Tag the submission version in the repo with a documented Git tag. | Administrative condition allowing the lecturer to inspect the final version. |
| 42 | MUST | Write and attach a comprehensive **academic report** as a readable file in the repo (model description, dilemmas, strategy, images, and RL curves if used). | Without the report the project is academically incomplete. |
| 43 | MUST | Download the submission form from Moodle, fill it in and save as PDF; do not alter or move fields. | Bureaucratic condition for receiving a grade. |
| 44 | MUST | Submit the assignment on Moodle **separately for each team member**. | A project without individual submission earns the student no grade. |
| 45 | MUST | Enter a unique **eight-character** team identification code, with no spaces. | Organisational failure preventing automatic attribution of reports. |

## Group 6 — Additions found when cross-checking the book

| # | Class | Rule | Source |
|---|---|---|---|
| 46 | MUST | A barrier placed on the cell where the thief currently stands **counts as a capture** (the cop wins). | Ch. 3 |
| 47 | MUST | A thief imprisoned with no legal move whatsoever also **counts as captured**. | Ch. 3 |
| 48 | MUST | Score every end scenario per the scoring table (capture 20/5, survival 5/10, technical loss 0/0). | Ch. 3 + parameter table |
| 49 | MUST | Submit **two separate GitHub repos** — cop and thief — with a cross-link in the README, two links in the Moodle submission, and four links in both teams' JSON. | Ch. 9 |
| 50 | MUST | Include in each repo, at minimum: `README`, config files (`config/`), **PRD files**, a **PLAN** file and **TODO** files. | Ch. 9 |
| 51 | MUST | Send the automatic final reports to the lecturer's agent-reporting address. | Ch. 9 |
| 52 | MUST | Play exactly **one counted game per opponent** (no repeats to accumulate points); uncounted warm-up games are permitted. | Ch. 9 |
| 53 | MUST | Record in the Step-0 declaration the **commit hash** that was played. Code may change between games, but every game must update the commit hash. | Ch. 5 |
| 54 | MUST | Report in the final JSON the **total tokens consumed** in the sub-game (and in the series). | Ch. 5, Ch. 9 |
| 55 | MUST | Self-score **code quality only** — not the league game result. | Ch. 11 |

---

## The fatal subset — check these before every commit and every game

These are the rules where the penalty is a zero or a disqualification rather than a lost point.

1. **Two separate processes, no shared memory** (1, 2)
2. **Live GUI shows local truth only, never the objective board** (8, 9)
3. **Config byte-identical; minimums never lowered** (11, 12)
4. **Barrier placements declared truthfully** (15, 16)
5. **SHA-256 commit-reveal present; nonce secret until game end; any mismatch = 0** (17, 18, 19)
6. **Replay verifier app exists** (20)
7. **Never lie about a capture, in either direction** (21, 22)
8. **Scent model cryptographically locked pre-game** (23)
9. **Natural language only — no numeric position protocol** (26, 27)
10. **Gmail send-only scope** (30)
11. **Both teams report, and the reports must agree** (35)
12. **No secrets in the repo, ever; `.gitignore` in place** (39, 40)
13. **Minimum opponents met; game count declared honestly** (31, 38)
14. **JSON attachment, not free text** (34)

## Precedence

1. **Appendix F (the parameter table) is the sole source of truth for every numeric value.** Nothing in the book body, in an example, or in the reference repo overrides it.
2. Illustrations, code samples, examples and scenarios in the book are **illustrative only**. They are not binding unless explicitly stated to be part of the game rules.
3. Where the book contradicts itself, the student has academic freedom to choose one reading — **provided the contradiction, the choice and the reasoning are documented explicitly in the report**.
4. Where the reference repo (`Game-P2P-Cop-Chase`) deviates from the book, **the book and the parameter table win**.
