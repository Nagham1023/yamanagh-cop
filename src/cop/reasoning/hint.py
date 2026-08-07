"""Hint generation + interpretation — two halves of the same turn.

Rule 25's "text processing and behavioural profiling only" boundary lives
here: this module can call an LLM (via `HintProvider`), but the actual
belief update and move decision stay pure Python, unchanged from PRD 3.
`interpret_hint` is simple, deterministic keyword matching — no LLM needed,
which is what keeps PRD 4's milestone testable locally (Design Question 4).
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


def dominant_scent_direction(
    sampled: dict[Position, float], own_pos: Position, board_size: int
) -> tuple[str, str] | None:
    """The (vertical, horizontal) **absolute board quadrant** where the
    sender's own scent mass — fresh deposit plus residual history,
    `own_pos` included — is concentrated (Revision 2). Same north/south x
    west/east convention `tools/hint_providers.py::_quadrant` uses (row/col
    compared against `board_size / 2`), which is exactly why this needed
    fixing: `interpret_hint` decodes direction words into that same
    absolute convention regardless of who sent them, and Revision 1's
    original version here summed neighbours *relative to* `own_pos`
    (excluding it) — a lagging trail-direction indicator, not an absolute
    region. "Scent strongest to my north-east" and "I am in the board's
    north-east" are different claims; ch. 4.4's own worked example reasons
    entirely over absolute cell coordinates ("south-east cell (1,4):
    τ=0.81... cells in the board's north: τ=0.00"), confirming the
    absolute reading is the book-correct one, not an invented fix.

    The fresh kernel deposit (0.9 at centre) usually dominates, so this
    reduces in practice to "the sender's own true quadrant, reported
    honestly" — but near a quadrant boundary, residual history can still
    outvote the fresh deposit, a real edge case kept rather than
    collapsed into a copy of `generate_hint`'s truthful branch.

    Returns `None` when `sampled` is genuinely all-zero — no scent
    anywhere, not even at `own_pos` — matching Revision 1's sentinel.
    """
    half = board_size / 2
    north = south = west = east = 0.0
    for cell, value in sampled.items():
        if cell.row < half:
            north += value
        else:
            south += value
        if cell.col < half:
            west += value
        else:
            east += value
    if north == south == west == east == 0.0:
        return None
    vertical = "north" if north >= south else "south"
    horizontal = "west" if west >= east else "east"
    return vertical, horizontal


_NO_SCENT_REPORT = "No scent detected."


def is_no_scent_report(text: str) -> bool:
    """True when `text` is `generate_scent_report`'s own no-signal sentinel.
    The receiver must skip `BeliefMap.update_from_scent_report` entirely in
    that case, not fall back to `interpret_hint`'s own north-west default —
    that would manufacture a weak, wrong signal from genuine absence of
    information (see `dominant_scent_direction`)."""
    return text == _NO_SCENT_REPORT


def generate_scent_report(sampled: dict[Position, float], own_pos: Position, config: GameConfig) -> str:
    """A short, deterministic, always-truthful natural-language report of
    the sender's own scent trail (Revision 1) — never routed through
    `HintProvider`/`choose_provider`/any LLM, regardless of `[trash_talk]
    provider`. A declared-truthful channel routed through a possibly-
    nondeterministic model would undermine the one property
    ("uncorruptible") the whole corroboration mechanic depends on. Same
    hard backstop-truncation discipline as `generate_hint`."""
    direction = dominant_scent_direction(sampled, own_pos, config.board_size)
    text = _NO_SCENT_REPORT if direction is None else f"Scent strongest to the {direction[0]} {direction[1]}."
    words = text.split()
    if len(words) > config.hint_word_limit:
        text = " ".join(words[: config.hint_word_limit])
    return text


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
