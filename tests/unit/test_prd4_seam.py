"""PRD 4 seam check, revised for the layer's own partial swap (Design
Question 3): `reasoning/subgame.py` has two sites (initial value, per-round
refresh) that deliberately keep routing through `ground_truth_target_position`
— it's PRD 3's algorithm-correctness sandbox, always ground truth by
design. The live `Orchestrator` path mirrors that same init+refresh shape
but on the belief-driven side instead: `orchestrator.py`'s constructor sets
the initial value, `orchestrator_turn.py`'s `take_turn()` refreshes it every
turn — both now read `self.belief_map.most_likely_cell()`, neither routes
through the seam. Found via this test itself: the original draft only
accounted for `orchestrator.py`'s site and missed `orchestrator_turn.py`'s
per-turn refresh, which is exactly the kind of unaccounted-for third site
this test exists to catch.

This asserts the swap actually happened on both known non-seam sites (a
positive check, not just "stopped failing"), and that no *other* file
quietly grows a target_pos assignment outside these two known pairs.

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
SUBGAME_PATH = SRC_ROOT / "reasoning" / "subgame.py"
ORCHESTRATOR_PATH = SRC_ROOT / "orchestrator.py"
ORCHESTRATOR_TURN_PATH = SRC_ROOT / "orchestrator_turn.py"
PEER_TRACE_PATH = SRC_ROOT / "integrity" / "peer_trace.py"


def _is_seam_call(node: ast.AST | None) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == SEAM_FUNCTION
    )


def _find_target_pos_assignments(tree: ast.Module) -> list[tuple[int, bool]]:
    """Return `(line, routes_through_seam)` for every `target_pos` assignment."""
    sites: list[tuple[int, bool]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "target_pos":
            sites.append((node.value.lineno, _is_seam_call(node.value)))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "target_pos":
                    sites.append((node.lineno, _is_seam_call(node.value)))
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Attribute)
            and node.target.attr == "target_pos"
            and node.value is not None
        ):
            sites.append((node.lineno, _is_seam_call(node.value)))
    return sites


def _sites_in(path: Path) -> list[tuple[int, bool]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return _find_target_pos_assignments(tree)


def test_subgame_still_routes_both_target_pos_sites_through_the_ground_truth_seam():
    sites = _sites_in(SUBGAME_PATH)
    assert len(sites) == 2, f"expected exactly 2 target_pos sites in subgame.py, found {sites}"
    assert all(routes for _, routes in sites), (
        "subgame.py's target_pos assignments must stay ground-truth — it's PRD 3's "
        "algorithm-correctness sandbox, deliberately unaffected by PRD 4"
    )


def test_orchestrator_no_longer_routes_target_pos_through_the_ground_truth_seam():
    sites = _sites_in(ORCHESTRATOR_PATH)
    assert len(sites) == 1, f"expected exactly 1 target_pos site in orchestrator.py, found {sites}"
    ((_, routes),) = sites
    assert not routes, (
        "orchestrator.py's target_pos should now come from self.belief_map.most_likely_cell() "
        "(PRD 4 Design Question 3) — this is a positive check that the swap actually happened"
    )


def test_orchestrator_turn_no_longer_routes_target_pos_through_the_ground_truth_seam():
    sites = _sites_in(ORCHESTRATOR_TURN_PATH)
    assert len(sites) == 1, f"expected exactly 1 target_pos site in orchestrator_turn.py, found {sites}"
    ((_, routes),) = sites
    assert not routes, (
        "orchestrator_turn.py's per-turn target_pos refresh should also come from "
        "self.belief_map.most_likely_cell(), same as orchestrator.py's initial value"
    )


def test_peer_trace_routes_its_throwaway_target_pos_through_the_ground_truth_seam():
    # PRD 7: run_peer_audit's GameState reconstruction never reads target_pos
    # at all (only own_pos/steps_taken/barriers feed canonical_state_bytes) —
    # neither ground-truth nor belief-driven, so it's routed through the
    # seam's own identity function rather than left bare, keeping it honest
    # about being a pass-through value, not a third semantic category.
    sites = _sites_in(PEER_TRACE_PATH)
    assert len(sites) == 1, f"expected exactly 1 target_pos site in peer_trace.py, found {sites}"
    ((_, routes),) = sites
    assert routes, "peer_trace.py's throwaway target_pos should route through the seam function"


def test_no_other_file_has_grown_an_unaccounted_for_target_pos_assignment():
    known = {SUBGAME_PATH, ORCHESTRATOR_PATH, ORCHESTRATOR_TURN_PATH, PEER_TRACE_PATH}
    unexpected = []
    for path in SRC_ROOT.rglob("*.py"):
        if path in known:
            continue
        sites = _sites_in(path)
        if sites:
            unexpected.append((str(path.relative_to(SRC_ROOT)), sites))
    assert unexpected == [], f"unaccounted-for target_pos assignments: {unexpected}"


def test_the_seam_function_itself_exists_and_is_currently_the_identity():
    from cop.domain.board import Position
    from cop.reasoning.state import ground_truth_target_position

    true_pos = Position(3, 3)
    assert ground_truth_target_position(true_pos) is true_pos
