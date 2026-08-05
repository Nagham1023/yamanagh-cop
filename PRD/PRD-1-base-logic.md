# PRD 1 — Base Logic

Status: **Done.** Retrospective writeup — this records what was built and verified, in the same shape as PLAN.md §5 so the two can be cross-checked against each other.

## Build

The grid, the movement set, barrier placement and quota, capture detection, scoring, the end conditions. Single process, no network, no AI, no crypto.

## Explicitly out of scope

- Two processes or MCP of any kind (PRD 2)
- A strategy module, heuristics, or Q-learning (PRD 3)
- Natural language, scent, hints, or an LLM call of any kind (PRD 4)
- ngrok/tunneling (PRD 5)
- Commit-Reveal, nonces, hashing, or Step-0 (PRD 6)
- The GUI, Replay app, Gmail, or the Gatekeeper (PRD 7)

## Rules owned

| Rule | Where it's implemented | Where it's tested |
|---|---|---|
| 12 — minimums raised only by agreement, never lowered | `config/shared/config_dev_g01.json` — verified against Appendix F via `check_config.py` (31/31 conform) | N/A (config validation, not unit-tested) |
| 13 — orthogonal moves only | `src/cop/domain/movement.py` — `DELTAS`, `is_legal_direction` | `tests/unit/test_movement.py` |
| 14 — no diagonals | same, diagonals absent from `DELTAS` by construction | `test_diagonal_move_is_rejected`, parametrized illegal-direction cases |
| 46 — barrier on thief's cell = capture | `src/cop/domain/capture.py::is_barrier_capture` | `tests/unit/test_capture.py` |
| 47 — thief with zero legal moves = capture | `src/cop/domain/capture.py::thief_has_no_legal_move` | `tests/unit/test_capture.py` (boxed-in, one-opening, open-field cases) |
| 48 — score every end scenario per Table 17 | `src/cop/domain/scoring.py::score_outcome` | `tests/unit/test_scoring.py` |
| I6 — no magic numbers, everything from config | `src/cop/shared/config.py::GameConfig` — fails loudly (`KeyError`) on a missing field rather than defaulting | `tests/unit/test_config.py::test_missing_required_field_raises` |

## Milestone

Two agents move legally on a 7×7 grid; a barrier placed beyond the 14-barrier quota is rejected; coordinate overlap between cop and thief triggers a capture.

Watched end-to-end via `scripts/watch_prd1.py` (not just `pytest` output) — all nine milestone/"also verify" checks passed live, per CLAUDE.md's definition of done.

## Also verified

- A barrier dropped on the thief's own cell registers as a capture (rule 46)
- A thief with zero legal moves registers as captured (rule 47)
- The cop cannot place a barrier further than one cell away, or off the board edge (`BarrierSet.can_place` — bounds-checking moved in-house after `TODO1.md`'s critical review found it was a real, reproducible hole, not just a documented deferral)
- A diagonal is rejected
- Capture, survival, and technical-loss all score correctly per Table 17, and technical loss is hard-fixed at (0, 0) independent of config
- Config values genuinely drive domain behaviour end-to-end, not just "no hardcoded literal in the source" (`tests/unit/test_config_wiring.py`)
- A config negotiating a coordinate convention other than the default (`origin`/`index_base`) fails loudly at load time instead of being silently misread

## Built & verified — summary

- `src/cop/domain/{board,movement,barriers,capture,scoring,end_conditions}.py`, `src/cop/shared/config.py`
- `config/shared/config_dev_g01.json`
- 54 tests in `tests/unit/` + `tests/integration/`, **100% coverage** on the code above (guide requires ≥85%)
- Four narrated demo scripts in `scripts/` — normal movement, diagonal rejection, barrier quota + declaration, capture ending the game (see `TODO.md` for exact run commands)
- `ruff check` — clean (scoped away from `.claude/`'s bundled skill scripts, which aren't project code)
- `check_config.py config/shared/config_dev_g01.json` — 31/31 parameters conform to Appendix F
- `rule-auditor` (spec-guard Mode 1) — **zero fatal violations**; rules 12, 13, 14, 46, 47, 48, I6 all reported CLEAN with file/test citations
- `TODO1.md` — a second, adversarial pass beyond the audit, which found and fixed one real bug and three coverage/validation gaps (see that file for detail)

## Carried forward to PRD 2

One item remains genuinely deferred — everything else `TODO1.md`'s critical review found was fixable inside PRD 1's own scope and has been fixed there (see `TODO1.md`).

1. **Barrier "forgo move" constraint** — a cop must give up its movement to place a barrier; `BarrierSet` enforces adjacency and bounds but not this, because turn state doesn't exist until PRD 2's sequencer.
