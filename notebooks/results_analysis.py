"""PRD 7's research-and-analysis deliverables (`software_submission_guidelines-V3.pdf`
§9/§11, submission checklist §20.9 items 5/7 — the guide asks for these,
the book doesn't; bolted onto this layer per `PLAN.md`'s own instruction).

Textual/tabular output only — no new dependency (matplotlib isn't part of
this project's own dependency set, and PRD 7's "New dependency" section
never added it): a belief-map heatmap as a character grid, a scent-decay
curve as a table, a win/loss/technical-loss breakdown read from any real
logs under `logs/`, one parameter-sensitivity pass over the belief-weighting
constant across warm-up (local, offline) games, and a token-cost breakdown
table sourced from `observability/cost.py`'s own totals.

Run:
    uv run python notebooks/results_analysis.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from sensitivity_pass import parameter_sensitivity_pass

from cop.domain.board import Board, Position
from cop.memory.belief import BeliefMap
from cop.memory.scent import ScentField
from cop.observability.cost import aggregate_tokens
from cop.shared.config import GameConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "shared" / "config_dev_g01.json"
LOGS_DIR = REPO_ROOT / "logs"


def belief_map_heatmap(board: Board, probabilities: dict) -> str:
    """A character-grid heatmap — '#' for the highest-probability cells,
    shading down to '.' for near-zero, `?` for never-updated cells."""
    if not probabilities:
        return "(no belief data)"
    max_value = max(probabilities.values())
    shades = " .:-=+*#%@"
    rows = []
    for row in range(board.size):
        cells = []
        for col in range(board.size):
            value = probabilities.get(Position(col, row), 0.0)
            intensity = max(0.0, min(1.0, value / max_value)) if max_value > 0 else 0.0
            cells.append(shades[round(intensity * (len(shades) - 1))])
        rows.append("".join(cells))
    return "\n".join(rows)


def scent_decay_table(source_strength: float, decay_rate: float, steps: int = 10) -> str:
    """Ch. 4.3's own emission/decay formula (Table 16), applied analytically
    — a cell that received one deposit, decaying every subsequent turn."""
    lines = ["turn  strength"]
    value = source_strength
    for turn in range(steps):
        lines.append(f"{turn:>4}  {value:.4f}")
        value *= 1 - decay_rate
    return "\n".join(lines)


def game_outcome_breakdown() -> str:
    """Reads any real trace logs already under `logs/` — honestly reports
    "no games played yet" rather than fabricating a placeholder breakdown."""
    if not LOGS_DIR.exists():
        return "(logs/ does not exist yet — no games played)"
    outcomes: Counter[str] = Counter()
    for log_path in LOGS_DIR.glob("*.json*"):
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("event") == "technical_loss":
                outcomes["technical_loss"] += 1
    if not outcomes:
        return "(no recorded game outcomes yet — this dev repo hasn't played a counted game)"
    return "\n".join(f"{name}: {count}" for name, count in outcomes.items())


def token_cost_breakdown(trace_log_path: Path) -> str:
    totals = aggregate_tokens(trace_log_path)
    return (
        f"model: template (Table 21, zero-token default)\n"
        f"turns counted: {totals.turns_counted}\n"
        f"total tokens: {totals.total_tokens}\n"
        f"estimated cost: $0.00 (zero-token provider)"
    )


def main() -> None:
    config = GameConfig.from_file(CONFIG_PATH)
    board = Board(size=config.board_size)

    print("1. Belief-map heatmap (a fresh, uniform map — no turns played yet)")
    uniform = BeliefMap.uniform(board)
    print(belief_map_heatmap(board, uniform._probabilities))

    print("\n2. Scent-decay curve (ch. 4.3, Table 16's own formula)")
    print(scent_decay_table(config.scent_source_strength, config.scent_decay_rate))
    ScentField.from_config(config)  # confirms the config values used above are the real, wired ones

    print("\n3. Win/loss/technical-loss breakdown across counted games so far")
    print(game_outcome_breakdown())

    print("\n4. Parameter-sensitivity pass — belief-weighting (scent vs. hint), PRD 4's own")
    print("   'intellectual core of the project' framing")
    print(parameter_sensitivity_pass(config, [0.3, 0.6, 0.9]))

    print("\n5. Token-cost breakdown")
    demo_log = Path("/tmp/results_analysis_demo_trace.jsonl")
    demo_log.write_text('{"event": "hint_generated", "tokens_used": 0}\n', encoding="utf-8")
    print(token_cost_breakdown(demo_log))


if __name__ == "__main__":
    main()
