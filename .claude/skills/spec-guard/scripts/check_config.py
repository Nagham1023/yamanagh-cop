#!/usr/bin/env python3
"""
check_config.py — validate a game config against the mandatory parameter table
(Appendix F) of the UoH Cop-and-Thief P2P final project.

Usage
-----
    python check_config.py config/game.json
    python check_config.py config/game.json --json          # machine-readable
    python check_config.py --identical cop/game.json thief/game.json

Checks performed
----------------
  FIXED       value must match exactly            -> violation if different
  MINIMUM     value may only be raised            -> violation if lower
  NEGOTIABLE  any value allowed                   -> note if absent (default applies)
  missing     a FIXED/MINIMUM key not found       -> violation (rule: code must
                                                    default to the table value,
                                                    so it has to be present)

  --identical  byte-for-byte comparison of two config files (rule 11).

Exit codes: 0 = clean, 1 = violations found, 2 = usage/parse error.

This script encodes only the parameter table. It does NOT check the 55 behavioural
rules in RULES.md — those need a reading of the code, not of the config.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from typing import Any


# --------------------------------------------------------------------------
# The mandatory parameter table, Appendix F.
# `aliases` lets the validator find the value even when a team names its keys
# differently. Add your own spellings here rather than editing `value`.
# --------------------------------------------------------------------------

@dataclass
class Param:
    key: str
    value: Any
    status: str                       # FIXED | MINIMUM | NEGOTIABLE
    table: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""


TABLE: list[Param] = [
    # Table 13 — board, coordinate system, start positions
    Param("board_size", 7, "MINIMUM", "13 board",
          ("board", "grid_size", "size", "n", "board_side")),
    Param("agent_count", 2, "FIXED", "13 board",
          ("agents", "num_agents", "players")),
    Param("origin", "top-left", "NEGOTIABLE", "13 board",
          ("coordinate_origin", "axis_origin")),
    Param("index_base", 0, "NEGOTIABLE", "13 board",
          ("axis_start_index", "start_index", "base_index")),
    Param("thief_start", [3, 3], "NEGOTIABLE", "13 board",
          ("thief_start_position", "start_thief", "thief_pos")),
    Param("cop_start", [0, 0], "NEGOTIABLE", "13 board",
          ("police_start", "cop_start_position", "start_cop", "police_pos")),

    # Table 14 — arena and verbal hints
    Param("arena", "New York", "NEGOTIABLE", "14 arena",
          ("game_arena", "region", "city")),
    Param("hint_word_limit", 15, "NEGOTIABLE", "14 arena",
          ("max_hint_words", "word_limit", "hint_max_words")),

    # Table 15 — movement and barriers
    Param("barrier_quota", 14, "MINIMUM", "15 movement",
          ("max_barriers", "barriers", "barrier_limit", "walls")),
    Param("step_ceiling", 35, "MINIMUM", "15 movement",
          ("max_steps", "max_moves", "step_limit", "turn_limit")),
    Param("survival_threshold", 35, "MINIMUM", "15 movement",
          ("survival_steps", "steps_to_survive", "survive_threshold")),

    # Table 16 — pheromones  (all FIXED and cryptographically locked, rule 23)
    Param("scent_source_strength", 0.9, "FIXED", "16 scent",
          ("scent_strength", "pheromone_strength", "scent_max", "emission")),
    Param("scent_decay_rate", 0.10, "FIXED", "16 scent",
          ("decay_rate", "scent_decay", "pheromone_decay", "decay")),
    Param("scent_field_size", 5, "FIXED", "16 scent",
          ("scent_window", "emission_window", "field_size", "scent_radius_window")),

    # Table 17 — scoring
    Param("score_capture_cop", 20, "FIXED", "17 scoring",
          ("capture_cop", "cop_capture_score", "police_capture")),
    Param("score_capture_thief", 5, "FIXED", "17 scoring",
          ("capture_thief", "thief_capture_score")),
    Param("score_survival_cop", 5, "FIXED", "17 scoring",
          ("survival_cop", "cop_survival_score", "police_survival")),
    Param("score_survival_thief", 10, "FIXED", "17 scoring",
          ("survival_thief", "thief_survival_score")),
    Param("score_draw", 2, "FIXED", "17 scoring",
          ("draw", "draw_score", "tie_score")),

    # Table 18 — network and league
    Param("sub_games_per_series", 6, "FIXED", "18 league",
          ("sub_games", "rounds", "games_per_series", "num_sub_games")),
    Param("diversity_reward", 10, "FIXED", "18 league",
          ("new_opponent_bonus", "diversity_bonus")),
    Param("min_games_to_pass", 2, "FIXED", "18 league",
          ("min_games", "minimum_games")),
    Param("token_estimate_per_series", 200000, "NEGOTIABLE", "18 league",
          ("token_budget", "max_tokens", "token_estimate")),
    Param("max_games_per_team", 10, "FIXED", "18 league",
          ("max_games", "game_cap")),

    # Table 19 — gatekeeper
    Param("requests_per_minute", 30, "MINIMUM", "19 gatekeeper",
          ("rpm", "rate_limit", "max_rpm")),
    Param("parallel_requests", 2, "MINIMUM", "19 gatekeeper",
          ("concurrency", "max_parallel", "max_concurrent")),
    Param("retry_delay_seconds", 5, "MINIMUM", "19 gatekeeper",
          ("retry_delay", "backoff", "backoff_seconds")),
    Param("retries", 3, "MINIMUM", "19 gatekeeper",
          ("max_retries", "retry_count", "attempts")),
    Param("queue_depth", 100, "MINIMUM", "19 gatekeeper",
          ("queue_size", "max_queue")),
    Param("response_timeout_seconds", 30, "NEGOTIABLE", "19 gatekeeper",
          ("timeout", "response_timeout", "request_timeout")),
    Param("watchdog_threshold_seconds", 60, "NEGOTIABLE", "19 gatekeeper",
          ("watchdog", "watchdog_timeout", "watchdog_threshold")),
]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten nested dicts into {dotted.path: value}, keeping leaf lists intact."""
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                out.update(flatten(v, path))
            else:
                out[path] = v
    return out


def lookup(flat: dict[str, Any], param: Param) -> tuple[str | None, Any]:
    """Find a param by canonical name or alias, matching on the last path segment."""
    names = {param.key.lower(), *(a.lower() for a in param.aliases)}
    for path, value in flat.items():
        if path.split(".")[-1].lower() in names:
            return path, value
    return None, None


def as_number(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


# --------------------------------------------------------------------------
# Core check
# --------------------------------------------------------------------------

def check(config: dict) -> dict:
    flat = flatten(config)
    violations: list[dict] = []
    notes: list[dict] = []
    ok: list[str] = []

    for p in TABLE:
        path, actual = lookup(flat, p)

        if path is None:
            if p.status in ("FIXED", "MINIMUM"):
                violations.append({
                    "rule": "missing",
                    "param": p.key,
                    "table": p.table,
                    "status": p.status,
                    "expected": p.value,
                    "actual": None,
                    "message": (
                        f"{p.key} is absent. Appendix F requires every value to be "
                        f"defined in the config file and cryptographically locked "
                        f"(mandatory rule 1)."
                    ),
                })
            else:
                notes.append({
                    "param": p.key,
                    "table": p.table,
                    "message": (
                        f"{p.key} not found — the code must default to "
                        f"{p.value!r}. Confirm that it does."
                    ),
                })
            continue

        if p.status == "FIXED":
            if actual != p.value:
                # tolerate 0.1 vs 0.10 style float noise
                a, e = as_number(actual), as_number(p.value)
                if a is not None and e is not None and abs(a - e) < 1e-9:
                    ok.append(p.key)
                    continue
                violations.append({
                    "rule": "FIXED",
                    "param": p.key,
                    "path": path,
                    "table": p.table,
                    "status": p.status,
                    "expected": p.value,
                    "actual": actual,
                    "message": (
                        f"{p.key} is FIXED at {p.value!r} but the config says "
                        f"{actual!r}. Any deviation from a FIXED value disqualifies "
                        f"the team."
                    ),
                })
            else:
                ok.append(p.key)

        elif p.status == "MINIMUM":
            a, e = as_number(actual), as_number(p.value)
            if a is None or e is None:
                violations.append({
                    "rule": "MINIMUM",
                    "param": p.key,
                    "path": path,
                    "table": p.table,
                    "status": p.status,
                    "expected": p.value,
                    "actual": actual,
                    "message": f"{p.key} should be numeric; got {actual!r}.",
                })
            elif a < e:
                violations.append({
                    "rule": "MINIMUM",
                    "param": p.key,
                    "path": path,
                    "table": p.table,
                    "status": p.status,
                    "expected": p.value,
                    "actual": actual,
                    "message": (
                        f"{p.key} is {actual!r}, below the binding minimum "
                        f"{p.value!r}. Minimums may be raised by mutual agreement, "
                        f"never lowered (rule 12)."
                    ),
                })
            else:
                ok.append(p.key)
                if a > e:
                    notes.append({
                        "param": p.key,
                        "table": p.table,
                        "message": (
                            f"{p.key} raised to {actual!r} from the {p.value!r} "
                            f"floor. Legal only if the opponent agreed — confirm "
                            f"it is in the signed shared config."
                        ),
                    })

        else:  # NEGOTIABLE
            ok.append(p.key)

    # cross-parameter sanity: start positions must sit on the board
    bpath, board = lookup(flat, TABLE[0])
    bn = as_number(board)
    if bn:
        for pname in ("thief_start", "cop_start"):
            p = next(x for x in TABLE if x.key == pname)
            _, pos = lookup(flat, p)
            if isinstance(pos, (list, tuple)) and len(pos) == 2:
                if any(not isinstance(c, int) or c < 0 or c >= bn for c in pos):
                    violations.append({
                        "rule": "consistency",
                        "param": pname,
                        "table": "13 board",
                        "status": "NEGOTIABLE",
                        "expected": f"coordinates within 0..{int(bn) - 1}",
                        "actual": pos,
                        "message": (
                            f"{pname} {pos!r} is off a {int(bn)}x{int(bn)} board."
                        ),
                    })

    return {"violations": violations, "notes": notes, "ok": ok}


# --------------------------------------------------------------------------
# Byte-identity check (rule 11)
# --------------------------------------------------------------------------

def identical(path_a: str, path_b: str) -> int:
    a = open(path_a, "rb").read()
    b = open(path_b, "rb").read()
    ha = hashlib.sha256(a).hexdigest()
    hb = hashlib.sha256(b).hexdigest()
    print(f"  {path_a}\n    sha256 {ha}")
    print(f"  {path_b}\n    sha256 {hb}")
    if a == b:
        print("\n  PASS - byte-for-byte identical (rule 11 satisfied).")
        return 0
    print("\n  FAIL - files differ. Rule 11 is FATAL: a game played on "
          "non-identical configs is voided for broken symmetry.")
    if json.loads(a) == json.loads(b):
        print("  Note: the parsed JSON is equal, so the difference is whitespace, "
              "key order, or line endings. Re-serialise both sides with "
              "sort_keys=True and separators=(',', ':').")
    return 1


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Validate a config against the mandatory parameter table "
                    "(Appendix F)."
    )
    ap.add_argument("config", nargs="?", help="path to the config JSON")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--identical", nargs=2, metavar=("A", "B"),
                    help="byte-compare two config files (rule 11)")
    args = ap.parse_args()

    if args.identical:
        print("\nRule 11 - config must be byte-for-byte identical on both sides\n")
        return identical(*args.identical)

    if not args.config:
        ap.print_help()
        return 2

    try:
        with open(args.config, encoding="utf-8") as fh:
            config = json.load(fh)
    except FileNotFoundError:
        print(f"error: no such file: {args.config}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: {args.config} is not valid JSON: {exc}", file=sys.stderr)
        return 2

    result = check(config)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if result["violations"] else 0

    v, n, ok = result["violations"], result["notes"], result["ok"]
    print(f"\nspec-guard - Appendix F check on {args.config}")
    print(f"  {len(ok)} of {len(TABLE)} parameters conform\n")

    if v:
        print(f"  {len(v)} VIOLATION(S)\n")
        for item in v:
            print(f"  [{item['rule']}] {item['param']}  (table {item['table']})")
            print(f"      expected: {item['expected']!r}")
            print(f"      actual:   {item['actual']!r}")
            print(f"      {item['message']}\n")

    if n:
        print(f"  {len(n)} note(s)\n")
        for item in n:
            print(f"  - {item['param']}: {item['message']}")
        print()

    if not v:
        print("  PASS - no violations of the mandatory parameter table.")
        print("  Reminder: this checks numbers only. The 55 behavioural rules in")
        print("  RULES.md still need a reading of the code.\n")
        return 0

    print("  FAIL - fix the violations above before playing or committing.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
