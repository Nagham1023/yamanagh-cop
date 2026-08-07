"""Hint generation + interpretation — two halves of the same turn.

Rule 25's "text processing and behavioural profiling only" boundary lives
here: this module can call an LLM (via `HintProvider`), but the actual
belief update and move decision stay pure Python, unchanged from PRD 3.
`interpret_hint` is simple, deterministic keyword matching — no LLM needed,
which is what keeps PRD 4's milestone testable locally (Design Question 4).

PRD 4 "Revision 3" (`todoFullFix.md` §C5): the scent-report language
mechanism that used to live here (`dominant_scent_direction`,
`generate_scent_report`, `is_no_scent_report`) is gone — the opponent's
scent field now crosses the wire as structured numeric data via a dedicated
MCP tool (`tools/mcp_server.py`'s `share_scent_map`), not a compass-
direction sentence squeezed through this module's text pipeline. This
module now only ever handles the natural-language tactical hint.
"""

from __future__ import annotations

import random

from ..domain.board import Board, Position
from ..shared.config import GameConfig
from ..tools.hint_providers import HintProvider


def decide_intent(lie_probability: float, rng: random.Random) -> bool:
    """True = send a truthful hint, False = a deliberate lie.

    Simple, config-driven-style policy, not strategically sophisticated —
    heuristic quality here is a later-PRD concern (PLAN.md's own "optional
    if time permits" framing for strategy refinement). `rng`/`lie_probability`
    are explicit parameters (no hidden global random state) so a test can
    force a deterministic value: `lie_probability=1.0` always lies,
    `lie_probability=0.0` never does — the milestone needs `Intent=False`
    on demand, not a "sometimes" policy.
    """
    return rng.random() >= lie_probability


def generate_hint(true_pos: Position, provider: HintProvider, config: GameConfig, intent: bool) -> str:
    """Ask `provider` for hint text, then enforce `hint_word_limit` as a hard
    backstop even if the provider already tried to respect it — never trust
    a single enforcement layer for a fatal rule (27)."""
    text = provider.generate(true_pos, intent, config.arena, config.hint_word_limit, config.board_size)
    words = text.split()
    if len(words) > config.hint_word_limit:
        text = " ".join(words[: config.hint_word_limit])
    return text


def choose_provider(
    step_number: int,
    configured_provider: HintProvider,
    template_provider: HintProvider,
    every_n_steps: int,
) -> HintProvider:
    """Table 21's `every_n_steps`: the configured (possibly expensive)
    provider only renders on cadence steps; every other step falls back to
    the zero-cost template renderer regardless of what's configured.
    `Intent` is still chosen and still logged every turn — only *which
    provider renders the text* is throttled."""
    if step_number % every_n_steps == 0:
        return configured_provider
    return template_provider


def interpret_hint(text: str, board: Board) -> Position:
    """Parse incoming text into a focal `Position` for `BeliefMap.update_from_hint`.

    Matches `TemplateHintProvider`'s own vocabulary (north/south/east/west) —
    deliberately simple, deterministic keyword matching, not an LLM call.
    Defaults to north-west when a direction isn't mentioned, rather than
    raising: an unparseable hint should degrade to "no new information",
    not crash the turn.
    """
    lowered = text.lower()
    vertical = "south" if "south" in lowered else "north"
    horizontal = "east" if "east" in lowered else "west"
    row = board.size // 4 if vertical == "north" else (3 * board.size) // 4
    col = board.size // 4 if horizontal == "west" else (3 * board.size) // 4
    return Position(col, row)
