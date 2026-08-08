"""Split out of `results_analysis.py` to stay under the repo's 150-line
house cap (`CLAUDE.md`) — the one function here carries a long design-
rationale docstring in its own right.
"""

from __future__ import annotations

from cop.domain.board import Board, Position
from cop.memory import belief as belief_module
from cop.memory.belief import BeliefMap
from cop.shared.config import GameConfig


def parameter_sensitivity_pass(
    config: GameConfig, reliabilities: list[float], threshold: float = 0.15, max_updates: int = 20
) -> str:
    """Varies `memory/belief.py::_HINT_RELIABILITY` and measures what it
    actually governs: how many *truthful, repeated* `update_from_hint` calls
    it takes `probability(true_point)` to cross `threshold`.

    `reasoning/subgame.py::run_local_subgame` was considered for this pass
    first, but it plays cop-brain-vs-ground-truth-target directly
    (`ground_truth_target_position`) and never constructs or consults a
    `BeliefMap` at all — varying `_HINT_RELIABILITY` would have had zero
    effect on its outcome. `BeliefMap.update_from_hint` (PRD 4's own
    "intellectual core of the project") is the actual mechanism this
    constant tunes, so this pass exercises it directly instead.

    `most_likely_cell()` was tried first as the convergence signal and
    rejected: `update_from_hint` applies one identical likelihood to every
    cell in the focal region (deliberately — Bayesian evidence about "near
    here," not "exactly here"), so a run of identical, truthful hints can
    never differentiate among those tied cells; `most_likely_cell()` just
    returns whichever tied cell iterates first, independent of reliability.
    `probability(true_point)` is a genuine, tie-free real number that rises
    monotonically toward `1/len(focal_region)` as reliability and repeated
    evidence do their job — a threshold below that asymptote is a real,
    reliability-sensitive convergence signal."""
    board = Board(size=config.board_size)
    true_point = Position(board.size // 2, board.size // 2)
    lines = [f"reliability  updates_to_cross_p={threshold:.2f}"]
    original = belief_module._HINT_RELIABILITY
    try:
        for reliability in reliabilities:
            belief_module._HINT_RELIABILITY = reliability
            belief = BeliefMap.uniform(board)
            updates = 0
            while belief.probability(true_point) < threshold and updates < max_updates:
                belief.update_from_hint(true_point, board)
                updates += 1
            reached = str(updates) if updates < max_updates else f">{max_updates}"
            lines.append(f"{reliability:.2f}         {reached}")
    finally:
        belief_module._HINT_RELIABILITY = original
    return "\n".join(lines)
