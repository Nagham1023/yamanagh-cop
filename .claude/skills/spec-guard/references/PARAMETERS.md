# The Mandatory Parameter Table — Appendix F

Source: book v3.0.0, Appendix F (טבלת הפרמטרים המחייבת). **This appendix is the single source of truth for every quantitative value in the project.** No number appearing in the book body, in a figure, in a code sample, or in the reference repo overrides it.

## Status semantics

| Status | Meaning |
|---|---|
| **FIXED** (קבוע) | Binding and unchangeable. Any deviation disqualifies the team. |
| **MINIMUM** (מינימום) | Negotiable **only in the direction that makes the game harder** — normally upward. Never below the listed value. Absent explicit agreement, the listed value is the default the code must use. |
| **NEGOTIABLE** (משא ומתן) | The parties may agree any value. Absent explicit agreement, the listed value is the default the code must use. |

---

## Table 13 — Board, coordinate system, start positions

| # | Parameter | Meaning | Value | Status |
|---|---|---|---|---|
| 1 | board size | side of the square game grid | **7 × 7** | MINIMUM |
| 2 | agent count | players in the race | **2** | FIXED |
| 3 | coordinate origin | corner where cell (0,0) sits | top-left | NEGOTIABLE |
| 4 | axis start index | number each axis counts from | **0** | NEGOTIABLE |
| 5 | thief start position | thief's opening cell | centre (3,3) | NEGOTIABLE |
| 6 | cop start position | cop's opening cell | corner (0,0) | NEGOTIABLE |

> Origin and index base are negotiable but **must be identical on both sides**. If one side counts from 0 and the other from 1, `[3,3]` means two different cells and the race falls apart.

## Table 14 — Game arena and verbal hints

| # | Parameter | Meaning | Value | Status |
|---|---|---|---|---|
| 1 | game arena | real-world region feeding real landmarks into the verbal hints. Empty string `""` = generic landmarks | `New York` | NEGOTIABLE |
| 2 | hint word limit | max words in any verbal hint sent over the network — applies to template mode **and** to the LLM (stated in its system prompt) | **15** | NEGOTIABLE |

## Table 15 — Movement and barriers

| # | Parameter | Meaning | Value | Status |
|---|---|---|---|---|
| 1 | movement set | 4 single orthogonal moves + stay; **no diagonals** | fixed set | FIXED |
| 2 | barrier quota | max barriers the cop may place | **14** | MINIMUM |
| 3 | step ceiling | max moves in a sub-game | **35** | MINIMUM |
| 4 | survival threshold | steps the thief must survive to win | **35** | MINIMUM |

## Table 16 — Dynamic pheromones

| # | Parameter | Meaning | Value | Status |
|---|---|---|---|---|
| 1 | scent strength at source | pheromone intensity in the emitting cell | **0.9** | FIXED |
| 2 | scent decay rate | decay proportion per turn | **0.10** | FIXED |
| 3 | scent field size | side of the emission window around the agent | **5 × 5** | FIXED |

> All three are FIXED **and** must be cryptographically locked before the game starts (rule 23). A deviation in the decay formula voids the game.

## Table 17 — Scoring

| # | Parameter | Meaning | Value | Status |
|---|---|---|---|---|
| 1 | capture score — cop | cop's score on a successful capture | **20** | FIXED |
| 2 | capture score — thief | thief's score when captured | **5** | FIXED |
| 3 | survival score — cop | cop's score when the thief survives | **5** | FIXED |
| 4 | survival score — thief | thief's score on successful survival | **10** | FIXED |
| 5 | draw score | score to each side when the aggregate across all sub-games against an opponent ends level | **2** | FIXED |

> Technical loss (crash, timeout, or cryptographic forgery) = **0 to both sides**.

## Table 18 — Network and league

| # | Parameter | Meaning | Value | Status |
|---|---|---|---|---|
| 1 | sub-games per series | sub-games in a series against one opponent | **6** | FIXED |
| 2 | diversity reward | score for a win against a **new** opponent | **10** | FIXED |
| 3 | minimum games to pass | minimum games per team for a passing grade | **2** | FIXED |
| 4 | token estimate per series | total LLM tokens a team may consume; actual consumption is reported by email | **~200,000** | NEGOTIABLE |
| 5 | max games per team | max games any team may play | **10** | FIXED |

## Table 19 — Network, rate limiter and protection (the Gatekeeper pattern)

| # | Parameter | Meaning | Value | Status |
|---|---|---|---|---|
| 1 | requests per minute | max outgoing API request rate | **30** | MINIMUM |
| 2 | parallel requests | max concurrent requests | **2** | MINIMUM |
| 3 | retry delay | wait before retrying after an error | **5 s** | MINIMUM |
| 4 | retries | attempts before declaring failure | **3** | MINIMUM |
| 5 | queue depth | request queue size under load | **100** | MINIMUM |
| 6 | response timeout | timeout per network request | **30 s** | NEGOTIABLE |
| 7 | watchdog threshold | idle time before the watchdog intervenes | **60 s** | NEGOTIABLE |

---

## Table 20 — Files, repository and addresses (reference only)

Not part of the negotiated config and not negotiable. File names derive from `game_id` and sub-game number `<NN>` so files from different games never mix.

| Variable | Role | Value |
|---|---|---|
| declaration file | pre-game declaration: teams, members, repos, hardware, model, tokens, times | `declaration_<game_id>.json` |
| config file | the agreed, cryptographically locked sub-game parameters | `config_<game_id>_g<NN>.json` |
| log file | sub-game log for cryptographic verification in the replay simulator | `log_<game_id>_g<NN>.json` |
| result file | final result report used by the lecturer to weight the league score | `result_<game_id>.json` |
| reference repo | the book's reference implementation | `https://github.com/rmisegal/Game-P2P-Cop-Chase` |
| lecturer address | general mail and GitHub repo sharing | `rmisegal@gmail.com` |
| agent reporting address | destination for the JSON reports the agent sends automatically | `rmisegal+uoh26finalgame@gmail.com` |

## Table 21 — LLM modes for the verbal game (private per peer, not negotiated)

Selected in the private config under `[trash_talk] provider`. **All four concern the deception text only — the move is always decided algorithmically in Python.**

| Mode | Where it runs / token cost | Rate limit | Account & setup |
|---|---|---|---|
| `template` *(default)* | in-process, pre-written sentences — **zero tokens** | none | none; offline and free |
| `ollama` | local model at `localhost:11434` — **zero API tokens** | none | install Ollama, pull a model |
| `claude_api` | small cloud model (Haiku) via API — real consumption counted against the token estimate | per account | Anthropic API key (paid) |
| `claude_cli` | `claude -p` via the Claude Code CLI — **highest cost** | per subscription | Claude CLI login (subscription) |

> `every_n_steps` invokes the model only once every N turns, reducing consumption further. In `template` and `ollama` modes the entire 6-sub-game series can be played at **zero tokens**, which throws the whole contest onto the quality of the movement algorithm.

## Table 22 — Strategy module selection (private per peer, not negotiated)

Movement policy — **the core of the grade** — is selected in the private config under `[strategy]`. Leaving the section empty runs the reference implementation's built-in heuristic brain.

| Key | Role | How to override |
|---|---|---|
| `thief_class` | your thief brain, written as `package.module:Class` | inherit from `ThiefBrain` / `BrainBase`, override `_pick_move` and/or `_decide_move` |
| `police_class` | your cop brain | same; in the cop's `_decide_move` the **barrier choice** is also made |

---

## The five mandatory rules attached to this table

1. Every team **must define all of the above values in the config file**, verify they are identical between the two teams, and **cryptographically lock them**.
2. A team may change the settings for each new game, as long as they match the agreement with the opposing team.
3. **Each config file must be given a different name per game**, so any game's configuration can be reconstructed easily.
4. **The config file of every game must be committed to the GitHub repo.**
5. Teams may change code between games; therefore **for every game an email must be sent to the lecturer containing the GitHub commit hash used in that game**.

## Quick reference — the default config in one block

```json
{
  "board_size": 7,
  "agent_count": 2,
  "origin": "top-left",
  "index_base": 0,
  "thief_start": [3, 3],
  "cop_start": [0, 0],
  "arena": "New York",
  "hint_word_limit": 15,
  "barrier_quota": 14,
  "step_ceiling": 35,
  "survival_threshold": 35,
  "scent_source_strength": 0.9,
  "scent_decay_rate": 0.10,
  "scent_field_size": 5,
  "score_capture_cop": 20,
  "score_capture_thief": 5,
  "score_survival_cop": 5,
  "score_survival_thief": 10,
  "score_draw": 2,
  "sub_games_per_series": 6,
  "diversity_reward": 10,
  "min_games_to_pass": 2,
  "token_estimate_per_series": 200000,
  "max_games_per_team": 10,
  "requests_per_minute": 30,
  "parallel_requests": 2,
  "retry_delay_seconds": 5,
  "retries": 3,
  "queue_depth": 100,
  "response_timeout_seconds": 30,
  "watchdog_threshold_seconds": 60
}
```

> Key names above are this skill's canonical names. If your implementation uses different names, keep the mapping in one place so the validator can still find them — the **values** are what bind you, not the spelling.
