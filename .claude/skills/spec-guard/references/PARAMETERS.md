# The Mandatory Parameter Table — Appendix ו, read against Appendix B's schema

Source: book v3.0.0, Appendix ו — the final appendix, "the single source of truth for every quantitative value in the project" (its own words, p.151). No number appearing in the book body, in a figure, in a code sample, or in the reference repo overrides it. **The field *names* below are Appendix B's** (`config/game.json`'s schema, p.126-132) — nested, not flat. Earlier versions of this doc used invented flat names (`board_size`, `barrier_quota`, ...); those were never transcribed from the book and are now corrected. This file is the schema's source of truth; `src/cop/shared/config.py`'s internal Python attribute names are a separate, private implementation detail — see the mapping table at the end.

## Status semantics

| Status | Meaning |
|---|---|
| **FIXED** (קבוע) | Binding and unchangeable. Any deviation disqualifies the team. |
| **MINIMUM** (מינימום) | Negotiable **only in the direction that makes the game harder** — normally upward. Never below the listed value. Absent explicit agreement, the listed value is the default the code must use. |
| **NEGOTIABLE** (משא ומתן) | The parties may agree any value. Absent explicit agreement, the listed value is the default the code must use. |

---

## Top-level: `schema_version`, `agreed_between`

Wholly new entries — no prior art in this repo before this correction pass. Not one of Appendix ו's numeric parameters; they're the config file's own self-identification.

| Field | Meaning | Example value | Status |
|---|---|---|---|
| `schema_version` | Version string of the config schema itself (Appendix B's own example: `"1.2"`) | `"1.2"` | FIXED — describes the schema, not negotiated between teams |
| `agreed_between` | The two teams' identifiers, for a human/audit trail | `["group-a", "group-b"]` | Descriptive metadata, not a game parameter — not checked by `check_config.py`'s numeric-value logic |

## `board_and_agents` — Table 13, board/coordinate system/start positions

| # | Field (`board_and_agents.<field>`) | Meaning | Value | Status |
|---|---|---|---|---|
| 1 | `grid_size` | side of the square game grid | **7 × 7** | MINIMUM |
| 2 | `num_agents` | players in the race | **2** | FIXED |
| 3 | `axis_origin_corner` | corner where cell (0,0) sits | `top-left` | NEGOTIABLE |
| 4 | `axis_start_index` | number each axis counts from | **0** | NEGOTIABLE |
| 5 | `thief_start` | thief's opening cell | `[3, 3]` | NEGOTIABLE |
| 6 | `cop_start` | cop's opening cell | `[0, 0]` | NEGOTIABLE |

> `axis_origin_corner` and `axis_start_index` are negotiable but **must be identical on both sides**. If one side counts from 0 and the other from 1, `[3,3]` means two different cells and the race falls apart.

## `world` — Table 14, game arena and verbal hints

| # | Field (`world.<field>`) | Meaning | Value | Status |
|---|---|---|---|---|
| 1 | `map_area` | real-world region feeding real landmarks into the verbal hints. Empty string `""` = generic landmarks | `"New York"` | NEGOTIABLE |
| 2 | `hint_max_words` | max words in any verbal hint sent over the network — applies to template mode **and** to the LLM (stated in its system prompt) | **15** | NEGOTIABLE |

## `movement_and_barriers` — Table 15

| # | Field (`movement_and_barriers.<field>`) | Meaning | Value | Status |
|---|---|---|---|---|
| 1 | `move_set` | 4 single orthogonal moves + stay; **no diagonals** | `["N","S","E","W","STAY"]` | FIXED |
| 2 | `max_barriers` | max barriers the cop may place | **14** | MINIMUM |
| 3 | `max_moves` | max moves in a sub-game | **35** | MINIMUM |
| 4 | `survival_threshold` | steps the thief must survive to win | **35** | MINIMUM |

## `pheromones` — Table 16, dynamic pheromones

| # | Field (`pheromones.<field>`) | Meaning | Value | Status |
|---|---|---|---|---|
| 1 | `pheromone_center_intensity` | pheromone intensity in the emitting cell | **0.9** | FIXED |
| 2 | `pheromone_decay` | decay proportion per turn | **0.10** | FIXED |
| 3 | `pheromone_grid_size` | side of the **single-deposit emission kernel** — the radial falloff pattern one `advance()` call paints around the agent's current cell (ch. 4.3, Fig. 4: centre τ=0.9 falling to 0.04 at the corners) | **5 × 5** | FIXED |

> All three are FIXED **and** must be cryptographically locked before the game starts (rule 23; ch. 4.5's negotiation ceremony — see `WIRE-CONTRACT.md`). A deviation in the decay formula voids the game.

> **Not a transmission window.** `pheromone_grid_size` bounds one deposit event's spatial shape, not how much of the accumulated field a peer may read or share. Ch. 4.4, read directly: "each agent can sample **the board** and receive its opponent's scent map" — and its own worked example reads a distant, explicitly-empty cell (τ=0.00) alongside a fresh one, which only makes sense over the board-wide accumulated trail, not a fixed 5×5 patch. `share_scent_map()`/`ScentField.full_field()` sending the whole field (unwindowed) is the book-correct reading of ch. 4.4, not a deviation from it — confirmed by two independent direct re-reads of ch. 4.3/4.4 (see `FULLFIX.md`'s "Rule 27 legal review"). This is worth stating explicitly because the two "5×5" concepts are easy to conflate — a claim that the opponent "receives a 5×5 scent grid" is describing the emission kernel, not what actually crosses the wire.

## `scoring` — Table 17

| # | Field (`scoring.<field>`) | Meaning | Value | Status |
|---|---|---|---|---|
| 1 | `capture_cop` | cop's score on a successful capture | **20** | FIXED |
| 2 | `capture_thief` | thief's score when captured | **5** | FIXED |
| 3 | `survival_cop` | cop's score when the thief survives | **5** | FIXED |
| 4 | `survival_thief` | thief's score on successful survival | **10** | FIXED |
| 5 | `tie_score` | score to each side when the aggregate across all sub-games against an opponent ends level | **2** | FIXED |
| 6 | `technical_loss` | score to both sides on a technical loss (crash, timeout, cryptographic forgery) | **0** | FIXED |

## `network_and_league` — Table 18

| # | Field (`network_and_league.<field>`) | Meaning | Value | Status |
|---|---|---|---|---|
| 1 | `response_timeout_sec` | timeout per network request | **30 s** | NEGOTIABLE |
| 2 | `watchdog_timeout_sec` | idle time before the watchdog intervenes | **60 s** | NEGOTIABLE |
| 3 | `num_games` | sub-games in a series against one opponent | **6** | FIXED |
| 4 | `diversity_reward` | score for a win against a **new** opponent | **10** | FIXED |
| 5 | `min_games_to_pass` | minimum games per team for a passing grade | **2** | FIXED |
| 6 | `max_games_per_team` | max games any team may play | **10** | FIXED |
| 7 | `token_budget_per_series` | total LLM tokens a team may consume; actual consumption is reported by email | **~200,000** | NEGOTIABLE |

## `rate_limiter_gatekeeper` — Table 19, the Gatekeeper pattern

| # | Field (`rate_limiter_gatekeeper.<field>`) | Meaning | Value | Status |
|---|---|---|---|---|
| 1 | `requests_per_minute` | max outgoing API request rate | **30** | MINIMUM |
| 2 | `concurrent_requests` | max parallel requests | **2** | MINIMUM |
| 3 | `retry_backoff_sec` | wait before retrying after an error | **5 s** | MINIMUM |
| 4 | `max_retries` | attempts before declaring failure | **3** | MINIMUM |
| 5 | `queue_depth` | request queue size under load | **100** | MINIMUM |

> Not yet consumed anywhere in `src/` — correctly deferred to PRD 7's `policy/gatekeeper.py` (see `PLAN.md` §5). Present here and in the config file so the values are locked and ready when that layer lands.

---

## Table 20 — Files, repository and addresses (reference only)

Not part of the negotiated config and not negotiable. File names derive from `game_id` and sub-game number `<NN>` so files from different games never mix.

| Variable | Role | Value |
|---|---|---|
| declaration file | pre-game declaration: teams, members, repos, hardware, model, tokens, times | `declaration_<game_id>.json` |
| config file | the agreed, cryptographically locked sub-game parameters | `config_<game_id>_g<NN>.json` |
| log file | sub-game log for cryptographic verification in the replay simulator | `log_<game_id>_g<NN>.json` |
| result file | final result report used by the lecturer to weight the league score | `result_<game_id>.json` |
| private per-peer file | never negotiated, never crosses the network, hand-edited | `config/game.toml` |
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

## Quick reference — the default config in one block, Appendix B's nested shape

```json
{
  "schema_version": "1.2",
  "agreed_between": ["group-a", "group-b"],
  "board_and_agents": {
    "grid_size": 7,
    "num_agents": 2,
    "thief_start": [3, 3],
    "cop_start": [0, 0],
    "axis_origin_corner": "top-left",
    "axis_start_index": 0
  },
  "world": {
    "map_area": "New York",
    "hint_max_words": 15
  },
  "movement_and_barriers": {
    "move_set": ["N", "S", "E", "W", "STAY"],
    "max_barriers": 14,
    "max_moves": 35,
    "survival_threshold": 35
  },
  "scoring": {
    "capture_cop": 20,
    "capture_thief": 5,
    "survival_cop": 5,
    "survival_thief": 10,
    "tie_score": 2,
    "technical_loss": 0
  },
  "pheromones": {
    "pheromone_center_intensity": 0.9,
    "pheromone_decay": 0.10,
    "pheromone_grid_size": 5
  },
  "network_and_league": {
    "response_timeout_sec": 30,
    "watchdog_timeout_sec": 60,
    "num_games": 6,
    "diversity_reward": 10,
    "min_games_to_pass": 2,
    "max_games_per_team": 10,
    "token_budget_per_series": 200000
  },
  "rate_limiter_gatekeeper": {
    "requests_per_minute": 30,
    "concurrent_requests": 2,
    "retry_backoff_sec": 5,
    "max_retries": 3,
    "queue_depth": 100
  }
}
```

## Mapping to this repo's internal code names

`src/cop/shared/config.py`'s `GameConfig` dataclass keeps its own flat, private Python attribute names — Appendix B governs the negotiated **file** schema, not either team's internal variable naming, and `GameConfig.from_dict()` is the one function that translates between them. This mapping is the only place that translation needs to be legible end-to-end:

| Appendix B nested path | Internal `GameConfig` attribute |
|---|---|
| `board_and_agents.grid_size` | `board_size` |
| `board_and_agents.num_agents` | `agent_count` |
| `board_and_agents.axis_origin_corner` | `origin` |
| `board_and_agents.axis_start_index` | `index_base` |
| `board_and_agents.thief_start` | `thief_start` |
| `board_and_agents.cop_start` | `cop_start` |
| `world.map_area` | `arena` |
| `world.hint_max_words` | `hint_word_limit` |
| `movement_and_barriers.max_barriers` | `barrier_quota` |
| `movement_and_barriers.max_moves` | `step_ceiling` |
| `movement_and_barriers.survival_threshold` | `survival_threshold` |
| `pheromones.pheromone_center_intensity` | `scent_source_strength` |
| `pheromones.pheromone_decay` | `scent_decay_rate` |
| `pheromones.pheromone_grid_size` | `scent_field_size` |
| `scoring.capture_cop` | `score_capture_cop` |
| `scoring.capture_thief` | `score_capture_thief` |
| `scoring.survival_cop` | `score_survival_cop` |
| `scoring.survival_thief` | `score_survival_thief` |
| `scoring.tie_score` | `score_draw` |
| `network_and_league.response_timeout_sec` | `response_timeout_seconds` |
| `network_and_league.watchdog_timeout_sec` | `watchdog_threshold_seconds` |
| `schema_version`, `agreed_between` | `schema_version`, `agreed_between` (stored verbatim, new fields) |

`movement_and_barriers.move_set`, `scoring.technical_loss`, every `network_and_league`/`rate_limiter_gatekeeper` league/gatekeeper field beyond the two timeouts above are validated by `check_config.py` and present in the file, but not yet read into `GameConfig` — correctly deferred (Table 18/19 league and rate-limiter fields are PRD 7 territory; `move_set`/`technical_loss` have no consuming code yet either). Not a gap introduced by this pass — confirmed pre-existing via the codebase audit that grounded this correction.

> `check_config.py`'s alias table still uses the *internal* names above as its canonical validator keys (see that script directly) — this file's nested names are what the config **file** must use; the validator's `lookup()` matches by last path segment regardless of nesting, so it finds `grid_size` under `board_and_agents` the same way it would find a bare `grid_size` key.

## Not on this table: the belief-map reliability coefficient

`src/cop/memory/belief.py`'s `_HINT_RELIABILITY`/`_SCENT_MAP_BOOST_SCALE` constants (`todoFullFix.md` §E) are **not** Appendix F/B parameters and are deliberately absent from this table and from `check_config.py`'s validated set. The book (ch. 6.4) gives the *concept* of a reliability coefficient on hint evidence, never a specific number — any concrete value is each team's own algorithm tuning, the same category as `movement.DELTAS` or `CopBrain`'s tie-break order, not a negotiated game rule Appendix F/B locks between the two teams. `check_config.py` should never gain a check for these; if a future revision adds one anyway, that's the bug, not this note.
