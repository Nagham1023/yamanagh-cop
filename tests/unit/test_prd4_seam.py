"""PRD 4 seam check: state.py's docstring claims PRD 4 replaces *where*
`target_pos` comes from, not `GameState`'s shape — this makes that claim
checkable instead of just asserted. Every place in `src/cop/` that assigns
a value to something named `target_pos` must route through
`ground_truth_target_position` (`reasoning/state.py`) — the one function
PRD 4 needs to change.

AST-based, not regex: distinguishes a real assignment/keyword-argument from
a type annotation or a parameter name sharing the same identifier.

Known blind spot (rule-auditor finding, closed structurally rather than
here): this only inspects keyword arguments and attribute assignments — a
positional `GameState(own, thief, barriers)` call would put a raw value
into `target_pos` without tripping either check. Closed by making
`GameState` `@dataclass(kw_only=True)` instead of teaching this test to
also parse positional call sites — see `test_state.py`'s
`test_positional_construction_is_rejected`.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent.parent / "src" / "cop"
SEAM_FUNCTION = "ground_truth_target_position"


def _is_seam_call(node: ast.AST | None) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == SEAM_FUNCTION
    )


def _find_target_pos_assignments(tree: ast.Module, file: Path) -> list[str]:
    """Return a description string for every `target_pos` assignment that
    does NOT route through the seam function."""
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "target_pos":
            if not _is_seam_call(node.value):
                violations.append(f"{file}:{node.value.lineno}: target_pos=... keyword argument")
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                is_target_pos_attr = isinstance(target, ast.Attribute) and target.attr == "target_pos"
                if is_target_pos_attr and not _is_seam_call(node.value):
                    violations.append(f"{file}:{node.lineno}: .target_pos = ... attribute assignment")
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Attribute)
            and node.target.attr == "target_pos"
            and node.value is not None
            and not _is_seam_call(node.value)
        ):
            violations.append(f"{file}:{node.lineno}: .target_pos: ... = ... annotated assignment")
    return violations


def test_every_target_pos_assignment_routes_through_the_single_ground_truth_seam():
    violations = []
    for path in SRC_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        violations.extend(_find_target_pos_assignments(tree, path.relative_to(SRC_ROOT)))

    assert violations == [], (
        "target_pos assigned outside ground_truth_target_position — PRD 4 would need to "
        "touch more than one call site:\n" + "\n".join(violations)
    )


def test_the_seam_function_itself_exists_and_is_currently_the_identity():
    from cop.domain.board import Position
    from cop.reasoning.state import ground_truth_target_position

    true_pos = Position(3, 3)
    assert ground_truth_target_position(true_pos) is true_pos
